import argparse
import csv
from pathlib import Path
import re
import sqlite3

try:
    from research_metrics import normalize_direction, target_column_for_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.ml_research
    from scripts.research_metrics import normalize_direction, target_column_for_direction
try:
    from feature_safety import is_excluded_model_feature
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.ml_research
    from scripts.feature_safety import is_excluded_model_feature
try:
    from time_split_utils import (
        apply_purge_train_test_split,
        downsample_non_overlapping_rows,
        parse_time_server,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.ml_research
    from scripts.time_split_utils import (
        apply_purge_train_test_split,
        downsample_non_overlapping_rows,
        parse_time_server,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "ml_research"
TABLE_NAME = "ml_dataset"
RANDOM_STATE = 42

REPORT_FILES = [
    "correlations.csv",
    "mutual_information.csv",
    "random_forest_importance.csv",
    "permutation_importance.csv",
    "model_metrics.csv",
    "threshold_analysis.csv",
    "feature_summary.csv",
]

THRESHOLD_ANALYSIS_LEVELS = (
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
)


def infer_horizon(*columns: str) -> int | None:
    for column in columns:
        match = re.search(r"_(\d+)$", column or "")
        if match:
            return int(match.group(1))
    return None


def default_output_dir(symbol: str, timeframe: str, horizon: int | None, direction: str) -> Path:
    horizon_text = f"h{horizon}" if horizon is not None else "hunknown"
    return DEFAULT_OUTPUT_DIR / direction / f"{symbol}_{timeframe}_{horizon_text}"


def load_dependencies():
    try:
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.feature_selection import mutual_info_classif
        from sklearn.inspection import permutation_importance
        from sklearn.metrics import (
            accuracy_score,
            average_precision_score,
            brier_score_loss,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Missing ML research dependencies. Install them with: "
            "python -m pip install pandas scikit-learn"
        ) from exc

    return {
        "np": np,
        "pd": pd,
        "RandomForestClassifier": RandomForestClassifier,
        "mutual_info_classif": mutual_info_classif,
        "permutation_importance": permutation_importance,
        "accuracy_score": accuracy_score,
        "average_precision_score": average_precision_score,
        "brier_score_loss": brier_score_loss,
        "f1_score": f1_score,
        "precision_score": precision_score,
        "recall_score": recall_score,
        "roc_auc_score": roc_auc_score,
    }


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def load_dataset(pd_module, db_path: Path, symbol: str, timeframe: str):
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        return pd_module.read_sql_query(
            f"""
            SELECT *
            FROM {TABLE_NAME}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time_server ASC
            """,
            connection,
            params=(symbol, timeframe),
        )


def prepare_numeric_features(pd_module, data, target_column: str, return_target: str):
    if target_column not in data.columns:
        raise ValueError(f"Target column not found: {target_column}")
    if return_target not in data.columns:
        raise ValueError(f"Return target column not found: {return_target}")

    filtered = data[data[target_column].notna()].copy()
    if filtered.empty:
        raise ValueError(f"No rows found after dropping NULL target values for {target_column}.")

    candidate_columns = [
        column
        for column in filtered.columns
        if column not in {target_column, return_target}
        and not is_excluded_model_feature(column)
    ]
    numeric_features = pd_module.DataFrame(index=filtered.index)
    for column in candidate_columns:
        converted = pd_module.to_numeric(filtered[column], errors="coerce")
        if converted.notna().any():
            numeric_features[column] = converted

    if numeric_features.empty:
        raise ValueError("No numeric feature columns available after exclusions.")

    y = pd_module.to_numeric(filtered[target_column], errors="coerce")
    returns = pd_module.to_numeric(filtered[return_target], errors="coerce")
    valid_y = y.notna()
    filtered = filtered.loc[valid_y].copy()
    numeric_features = numeric_features.loc[valid_y].copy()
    y = y.loc[valid_y].astype(int)
    returns = returns.loc[valid_y]

    non_constant_columns = [
        column for column in numeric_features.columns if numeric_features[column].nunique(dropna=True) > 1
    ]
    numeric_features = numeric_features[non_constant_columns]
    if numeric_features.empty:
        raise ValueError("No non-constant numeric feature columns available.")

    return filtered, numeric_features, y, returns


def directional_returns_for_direction(returns, direction: str):
    normalized_direction = normalize_direction(direction)
    if normalized_direction == "long":
        return returns.copy()
    return -returns


def build_feature_summary(pd_module, numeric_features):
    rows = []
    total = len(numeric_features)
    for column in numeric_features.columns:
        series = numeric_features[column]
        rows.append(
            {
                "feature": column,
                "non_null_count": int(series.notna().sum()),
                "missing_count": int(series.isna().sum()),
                "missing_ratio": float(series.isna().sum() / total) if total else 0.0,
                "unique_count": int(series.nunique(dropna=True)),
                "mean": series.mean(),
                "std": series.std(),
                "min": series.min(),
                "max": series.max(),
            }
        )
    return pd_module.DataFrame(rows).sort_values(
        ["missing_ratio", "feature"],
        ascending=[True, True],
    )


def build_correlations(pd_module, numeric_features, returns, directional_returns):
    rows = []
    for column in numeric_features.columns:
        pair = pd_module.DataFrame(
            {
                "feature_value": numeric_features[column],
                "return_target": returns,
                "directional_return_target": directional_returns,
            }
        ).dropna()
        if len(pair) < 3 or pair["feature_value"].nunique() <= 1:
            pearson = None
            spearman = None
            abs_pearson = None
            abs_spearman = None
            directional_pearson = None
            directional_spearman = None
            abs_directional_pearson = None
            abs_directional_spearman = None
        else:
            if pair["return_target"].nunique() <= 1:
                pearson = None
                spearman = None
                abs_pearson = None
                abs_spearman = None
            else:
                pearson = pair["feature_value"].corr(pair["return_target"], method="pearson")
                spearman = pair["feature_value"].corr(pair["return_target"], method="spearman")
                abs_pearson = abs(pearson) if pearson == pearson else None
                abs_spearman = abs(spearman) if spearman == spearman else None

            if pair["directional_return_target"].nunique() <= 1:
                directional_pearson = None
                directional_spearman = None
                abs_directional_pearson = None
                abs_directional_spearman = None
            else:
                directional_pearson = pair["feature_value"].corr(
                    pair["directional_return_target"],
                    method="pearson",
                )
                directional_spearman = pair["feature_value"].corr(
                    pair["directional_return_target"],
                    method="spearman",
                )
                abs_directional_pearson = (
                    abs(directional_pearson) if directional_pearson == directional_pearson else None
                )
                abs_directional_spearman = (
                    abs(directional_spearman) if directional_spearman == directional_spearman else None
                )

        rows.append(
            {
                "feature": column,
                "pearson": pearson,
                "abs_pearson": abs_pearson,
                "spearman": spearman,
                "abs_spearman": abs_spearman,
                "directional_pearson": directional_pearson,
                "abs_directional_pearson": abs_directional_pearson,
                "directional_spearman": directional_spearman,
                "abs_directional_spearman": abs_directional_spearman,
                "pair_count": len(pair),
            }
        )

    correlations = pd_module.DataFrame(rows)
    return correlations.sort_values(
        ["abs_directional_spearman", "abs_directional_pearson", "abs_spearman", "abs_pearson"],
        ascending=[False, False, False, False],
        na_position="last",
    )


def temporal_split(features, target, train_ratio: float = 0.7):
    split_index = int(len(features) * train_ratio)
    if split_index <= 0 or split_index >= len(features):
        raise ValueError("Not enough rows for a 70/30 temporal train/test split.")

    return (
        features.iloc[:split_index].copy(),
        features.iloc[split_index:].copy(),
        target.iloc[:split_index].copy(),
        target.iloc[split_index:].copy(),
    )


def row_refs_from_frame(frame) -> list[dict[str, object]]:
    return [
        {"time_server": row["time_server"], "__index": index}
        for index, row in frame[["time_server"]].iterrows()
    ]


def split_with_overlap_controls(
    filtered,
    features,
    target,
    *,
    timeframe: str,
    target_horizon: int,
    purge_overlap: bool,
    embargo_bars: int,
    non_overlap_eval: bool,
):
    x_train, x_test, y_train, y_test = temporal_split(features, target)
    metadata = {
        "purge_overlap": str(bool(purge_overlap)).lower(),
        "embargo_bars": int(embargo_bars),
        "non_overlap_eval": str(bool(non_overlap_eval)).lower(),
        "train_rows_before_purge": int(len(x_train)),
        "test_rows_before_embargo": int(len(x_test)),
    }

    if purge_overlap or embargo_bars > 0:
        train_times = filtered.loc[x_train.index, "time_server"].map(parse_time_server).dropna()
        test_times = filtered.loc[x_test.index, "time_server"].map(parse_time_server).dropna()
        if train_times.empty or test_times.empty:
            raise ValueError("Cannot apply purged split: time_server values are missing or invalid.")

        row_refs = row_refs_from_frame(filtered.loc[features.index])
        train_refs, test_refs = apply_purge_train_test_split(
            row_refs,
            train_start=train_times.iloc[0],
            train_end=train_times.iloc[-1],
            test_start=test_times.iloc[0],
            test_end=test_times.iloc[-1],
            timeframe=timeframe,
            target_horizon=target_horizon,
            purge_bars=None if purge_overlap else 0,
            embargo_bars=embargo_bars,
        )
        train_index = [row["__index"] for row in train_refs]
        test_index = [row["__index"] for row in test_refs]
        x_train = features.loc[train_index].copy()
        y_train = target.loc[train_index].copy()
        x_test = features.loc[test_index].copy()
        y_test = target.loc[test_index].copy()

    metadata["train_rows_after_purge"] = int(len(x_train))
    metadata["test_rows_after_embargo"] = int(len(x_test))

    if non_overlap_eval:
        test_refs = row_refs_from_frame(filtered.loc[x_test.index])
        sampled_refs = downsample_non_overlapping_rows(test_refs, timeframe, target_horizon)
        sampled_index = [row["__index"] for row in sampled_refs]
        x_test = x_test.loc[sampled_index].copy()
        y_test = y_test.loc[sampled_index].copy()

    metadata["test_rows_after_non_overlap"] = int(len(x_test))
    if x_train.empty or x_test.empty:
        raise ValueError("Overlap controls left an empty train or test split.")
    return x_train, x_test, y_train, y_test, metadata


def impute_features(x_train, x_test):
    medians = x_train.median(numeric_only=True)
    return (
        x_train.fillna(medians).fillna(0.0),
        x_test.fillna(medians).fillna(0.0),
    )


def class_balance(pd_module, target):
    counts = target.value_counts(dropna=False).sort_index()
    total = len(target)
    return pd_module.DataFrame(
        [
            {
                "target_value": value,
                "count": int(count),
                "ratio": float(count / total) if total else 0.0,
            }
            for value, count in counts.items()
        ]
    )


def build_mutual_information(pd_module, mutual_info_classif, x_train, y_train):
    scores = mutual_info_classif(
        x_train,
        y_train,
        random_state=RANDOM_STATE,
        discrete_features=False,
    )
    return pd_module.DataFrame(
        {"feature": x_train.columns, "mutual_information": scores}
    ).sort_values("mutual_information", ascending=False)


def train_random_forest(RandomForestClassifier, x_train, y_train):
    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    return model


def build_random_forest_importance(pd_module, model, feature_names):
    return pd_module.DataFrame(
        {
            "feature": feature_names,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)


def build_permutation_importance(pd_module, permutation_importance, model, x_test, y_test):
    result = permutation_importance(
        model,
        x_test,
        y_test,
        n_repeats=10,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    return pd_module.DataFrame(
        {
            "feature": x_test.columns,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)


def predict_positive_scores(model, x_test):
    if hasattr(model, "predict_proba") and len(model.classes_) == 2:
        return model.predict_proba(x_test)[:, 1], model.classes_[1]
    return None, None


def build_model_metrics(
    pd_module,
    model,
    x_train,
    x_test,
    y_train,
    y_test,
    metric_functions,
    metadata: dict[str, object],
):
    y_pred = model.predict(x_test)
    y_score, _positive_label = predict_positive_scores(model, x_test)

    roc_auc = None
    if y_score is not None and y_test.nunique() == 2:
        try:
            roc_auc = metric_functions["roc_auc_score"](y_test, y_score)
        except ValueError:
            roc_auc = None

    rows = [
        {"metric": "rows_total", "value": int(len(y_train) + len(y_test))},
        {"metric": "rows_train", "value": int(len(y_train))},
        {"metric": "rows_test", "value": int(len(y_test))},
        {"metric": "features_used", "value": int(x_train.shape[1])},
        {"metric": "train_positive_ratio", "value": float(y_train.mean())},
        {"metric": "test_positive_ratio", "value": float(y_test.mean())},
        {"metric": "accuracy", "value": metric_functions["accuracy_score"](y_test, y_pred)},
        {
            "metric": "precision",
            "value": metric_functions["precision_score"](y_test, y_pred, zero_division=0),
        },
        {
            "metric": "recall",
            "value": metric_functions["recall_score"](y_test, y_pred, zero_division=0),
        },
        {
            "metric": "f1",
            "value": metric_functions["f1_score"](y_test, y_pred, zero_division=0),
        },
        {"metric": "roc_auc", "value": roc_auc},
    ]
    for key, value in metadata.items():
        rows.append({"metric": key, "value": value})

    return pd_module.DataFrame(rows)


def build_threshold_analysis(
    pd_module,
    model,
    x_test,
    y_test,
    returns_test,
    directional_returns_test,
    metric_functions,
):
    y_score, positive_label = predict_positive_scores(model, x_test)
    if y_score is None:
        return pd_module.DataFrame(
            columns=[
                "threshold",
                "predicted_positive_count",
                "predicted_positive_ratio",
                "precision",
                "recall",
                "f1",
                "accuracy",
                "base_positive_ratio",
                "lift_vs_base_precision",
                "mean_return_target_for_predicted_positive",
                "median_return_target_for_predicted_positive",
                "mean_raw_return_target_for_predicted_positive",
                "median_raw_return_target_for_predicted_positive",
                "mean_directional_return_target_for_predicted_positive",
                "median_directional_return_target_for_predicted_positive",
                "average_precision_score",
                "brier_score_loss",
            ]
        )

    y_true_binary = (y_test == positive_label).astype(int)
    base_positive_ratio = float(y_true_binary.mean()) if len(y_true_binary) else 0.0

    average_precision = None
    if y_true_binary.nunique() == 2:
        try:
            average_precision = metric_functions["average_precision_score"](y_true_binary, y_score)
        except ValueError:
            average_precision = None

    brier_score = None
    try:
        brier_score = metric_functions["brier_score_loss"](y_true_binary, y_score)
    except ValueError:
        brier_score = None

    rows = []
    for threshold in THRESHOLD_ANALYSIS_LEVELS:
        y_pred_binary = (y_score >= threshold).astype(int)
        predicted_positive_count = int(y_pred_binary.sum())
        predicted_positive_ratio = float(predicted_positive_count / len(y_pred_binary)) if len(y_pred_binary) else 0.0
        selected_returns = returns_test[y_pred_binary == 1]
        selected_directional_returns = directional_returns_test[y_pred_binary == 1]
        precision = metric_functions["precision_score"](y_true_binary, y_pred_binary, zero_division=0)
        mean_raw_return = selected_returns.mean() if predicted_positive_count else None
        median_raw_return = selected_returns.median() if predicted_positive_count else None
        mean_directional_return = selected_directional_returns.mean() if predicted_positive_count else None
        median_directional_return = selected_directional_returns.median() if predicted_positive_count else None

        rows.append(
            {
                "threshold": threshold,
                "predicted_positive_count": predicted_positive_count,
                "predicted_positive_ratio": predicted_positive_ratio,
                "precision": precision,
                "recall": metric_functions["recall_score"](y_true_binary, y_pred_binary, zero_division=0),
                "f1": metric_functions["f1_score"](y_true_binary, y_pred_binary, zero_division=0),
                "accuracy": metric_functions["accuracy_score"](y_true_binary, y_pred_binary),
                "base_positive_ratio": base_positive_ratio,
                "lift_vs_base_precision": precision / base_positive_ratio if base_positive_ratio > 0 else None,
                "mean_return_target_for_predicted_positive": mean_raw_return,
                "median_return_target_for_predicted_positive": median_raw_return,
                "mean_raw_return_target_for_predicted_positive": mean_raw_return,
                "median_raw_return_target_for_predicted_positive": median_raw_return,
                "mean_directional_return_target_for_predicted_positive": mean_directional_return,
                "median_directional_return_target_for_predicted_positive": median_directional_return,
                "average_precision_score": average_precision,
                "brier_score_loss": brier_score,
            }
        )

    return pd_module.DataFrame(rows)


def write_reports(
    output_dir: Path,
    correlations,
    mutual_information,
    rf_importance,
    permutation,
    model_metrics,
    threshold_analysis,
    feature_summary,
    metadata: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    def with_metadata(frame):
        enriched = frame.copy()
        for key, value in reversed(list(metadata.items())):
            if key not in enriched.columns:
                enriched.insert(0, key, value)
        return enriched

    with_metadata(correlations).to_csv(output_dir / "correlations.csv", index=False)
    with_metadata(mutual_information).to_csv(output_dir / "mutual_information.csv", index=False)
    with_metadata(rf_importance).to_csv(output_dir / "random_forest_importance.csv", index=False)
    with_metadata(permutation).to_csv(output_dir / "permutation_importance.csv", index=False)
    model_metrics.to_csv(output_dir / "model_metrics.csv", index=False)
    with_metadata(threshold_analysis).to_csv(output_dir / "threshold_analysis.csv", index=False)
    with_metadata(feature_summary).to_csv(output_dir / "feature_summary.csv", index=False)


def print_top_features(pd_module, correlations, mutual_information, rf_importance, permutation):
    top = correlations[["feature", "abs_spearman", "abs_pearson"]].merge(
        mutual_information[["feature", "mutual_information"]],
        on="feature",
        how="outer",
    )
    top = top.merge(
        rf_importance[["feature", "importance"]].rename(columns={"importance": "random_forest_importance"}),
        on="feature",
        how="outer",
    )
    top = top.merge(
        permutation[["feature", "importance_mean"]].rename(columns={"importance_mean": "permutation_importance"}),
        on="feature",
        how="outer",
    )

    score_columns = [
        "abs_spearman",
        "abs_pearson",
        "mutual_information",
        "random_forest_importance",
        "permutation_importance",
    ]
    rank_columns = []
    for column in score_columns:
        rank_column = f"{column}_rank_score"
        top[rank_column] = 1 / top[column].rank(ascending=False, method="min")
        rank_columns.append(rank_column)

    top["interesting_score"] = top[rank_columns].sum(axis=1, skipna=True)
    top = top.sort_values("interesting_score", ascending=False)

    print("Top 20 feature candidates")
    display_columns = [
        "feature",
        "interesting_score",
        "abs_spearman",
        "abs_pearson",
        "mutual_information",
        "random_forest_importance",
        "permutation_importance",
    ]
    print(top[display_columns].head(20).to_string(index=False))


def run_research(args: argparse.Namespace) -> None:
    if args.embargo_bars < 0:
        raise ValueError("--embargo-bars cannot be negative.")

    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()
    direction = normalize_direction(args.direction)
    horizon = infer_horizon(args.return_target, args.target) or 10
    target_column = args.target or target_column_for_direction(direction, horizon)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else default_output_dir(symbol, timeframe, horizon, direction)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    deps = load_dependencies()
    pd_module = deps["pd"]

    data = load_dataset(pd_module, args.db_path, symbol, timeframe)
    if data.empty:
        raise ValueError(f"No ml_dataset rows found for {symbol} {timeframe}.")

    filtered, numeric_features, y, returns = prepare_numeric_features(
        pd_module,
        data,
        target_column,
        args.return_target,
    )
    directional_returns = directional_returns_for_direction(returns, direction)
    x_train, x_test, y_train, y_test, overlap_metadata = split_with_overlap_controls(
        filtered,
        numeric_features,
        y,
        timeframe=timeframe,
        target_horizon=horizon,
        purge_overlap=args.purge_overlap,
        embargo_bars=args.embargo_bars,
        non_overlap_eval=args.non_overlap_eval,
    )
    returns_test = returns.loc[x_test.index]
    directional_returns_test = directional_returns.loc[x_test.index]
    x_train, x_test = impute_features(x_train, x_test)

    if y_train.nunique() < 2:
        raise ValueError("Training target has only one class; cannot train classifier.")
    if y_test.nunique() < 2:
        print("Warning: test target has only one class; roc_auc may be unavailable.")

    correlations = build_correlations(pd_module, numeric_features, returns, directional_returns)
    feature_summary = build_feature_summary(pd_module, numeric_features)
    balance = class_balance(pd_module, y)
    balance_metadata = {}
    for row in balance.to_dict(orient="records"):
        value = row["target_value"]
        balance_metadata[f"class_{value}_count"] = row["count"]
        balance_metadata[f"class_{value}_ratio"] = row["ratio"]

    mutual_information = build_mutual_information(
        pd_module,
        deps["mutual_info_classif"],
        x_train,
        y_train,
    )
    model = train_random_forest(deps["RandomForestClassifier"], x_train, y_train)
    rf_importance = build_random_forest_importance(pd_module, model, x_train.columns)
    permutation = build_permutation_importance(
        pd_module,
        deps["permutation_importance"],
        model,
        x_test,
        y_test,
    )
    model_metrics = build_model_metrics(
        pd_module,
        model,
        x_train,
        x_test,
        y_train,
        y_test,
        {
            "accuracy_score": deps["accuracy_score"],
            "precision_score": deps["precision_score"],
            "recall_score": deps["recall_score"],
            "f1_score": deps["f1_score"],
            "roc_auc_score": deps["roc_auc_score"],
        },
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "target": target_column,
            "return_target": args.return_target,
            "horizon": horizon,
            "rows_after_target_filter": int(len(filtered)),
            **overlap_metadata,
            **balance_metadata,
        },
    )
    threshold_analysis = build_threshold_analysis(
        pd_module,
        model,
        x_test,
        y_test,
        returns_test,
        directional_returns_test,
        {
            "accuracy_score": deps["accuracy_score"],
            "average_precision_score": deps["average_precision_score"],
            "brier_score_loss": deps["brier_score_loss"],
            "precision_score": deps["precision_score"],
            "recall_score": deps["recall_score"],
            "f1_score": deps["f1_score"],
        },
    )

    write_reports(
        output_dir,
        correlations,
        mutual_information,
        rf_importance,
        permutation,
        model_metrics,
        threshold_analysis,
        feature_summary,
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "target": target_column,
            "return_target": args.return_target,
            "horizon": horizon,
            **overlap_metadata,
        },
    )

    print(f"Output directory: {output_dir}")
    print(f"Reports written to: {output_dir}")
    print_top_features(pd_module, correlations, mutual_information, rf_importance, permutation)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ML research reports on ml_dataset without creating trading signals."
    )
    parser.add_argument("--symbol", required=True, help="Symbol to analyze, for example EURUSD.")
    parser.add_argument("--timeframe", required=True, help="Timeframe to analyze, for example M15.")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--target", help="Classification target column. Default depends on --direction and horizon.")
    parser.add_argument("--return-target", default="future_return_10", help="Return column for correlations.")
    parser.add_argument("--purge-overlap", action="store_true")
    parser.add_argument("--embargo-bars", type=int, default=0)
    parser.add_argument("--non-overlap-eval", action="store_true")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory. Default: reports/ml_research/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{HORIZON}",
    )
    return parser.parse_args()


def main() -> int:
    try:
        run_research(parse_args())
    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ML research failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
