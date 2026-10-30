import argparse
import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "ml_research"
REPORT_FILES = [
    "correlations.csv",
    "mutual_information.csv",
    "random_forest_importance.csv",
    "permutation_importance.csv",
    "model_metrics.csv",
    "threshold_analysis.csv",
    "feature_summary.csv",
]


def print_csv_head(path: Path, rows_to_show: int = 5) -> None:
    print(f"{path.name}:")
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        for index, row in enumerate(reader):
            if index > rows_to_show:
                break
            print(", ".join(row))
    print()


def check_outputs(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    if not output_dir.exists():
        raise FileNotFoundError(f"ML research output directory not found: {output_dir}")
    if not output_dir.is_dir():
        raise NotADirectoryError(f"ML research output path is not a directory: {output_dir}")

    print(f"ML research output directory: {output_dir}")
    missing_files = []
    for file_name in REPORT_FILES:
        path = output_dir / file_name
        if not path.exists():
            missing_files.append(path)

    if missing_files:
        print("Missing report files:")
        for path in missing_files:
            print(f"- {path}")
        raise FileNotFoundError("One or more ML research report files are missing.")

    print("All expected report files exist.")
    print()
    for file_name in REPORT_FILES:
        print_csv_head(output_dir / file_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check generated ML research CSV reports.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Default: {DEFAULT_OUTPUT_DIR}")
    return parser.parse_args()


def main() -> int:
    try:
        check_outputs(parse_args().output_dir)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        print(f"ML research output check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
