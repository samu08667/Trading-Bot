"""Shared target-family naming for research-only preferred target branches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PREFERRED_2ATR_1ATR_HIT_FIRST = "preferred_2atr_1atr_hit_first"
PREFERRED_1_5ATR_1ATR_HIT_FIRST = "preferred_1_5atr_1atr_hit_first"


@dataclass(frozen=True)
class TargetFamilySpec:
    name: str
    tp_atr: float
    sl_atr: float


SUPPORTED_TARGET_FAMILIES: dict[str, TargetFamilySpec] = {
    PREFERRED_2ATR_1ATR_HIT_FIRST: TargetFamilySpec(
        name=PREFERRED_2ATR_1ATR_HIT_FIRST,
        tp_atr=2.0,
        sl_atr=1.0,
    ),
    PREFERRED_1_5ATR_1ATR_HIT_FIRST: TargetFamilySpec(
        name=PREFERRED_1_5ATR_1ATR_HIT_FIRST,
        tp_atr=1.5,
        sl_atr=1.0,
    ),
}

PREFERRED_TARGET_FAMILY_ORDER = (
    PREFERRED_1_5ATR_1ATR_HIT_FIRST,
    PREFERRED_2ATR_1ATR_HIT_FIRST,
)
BASELINE_TRIPLE_BARRIER_MULTIPLIERS = ((1.0, 1.0),)


def normalize_target_family(target_family: str) -> str:
    family = str(target_family or "").strip().lower()
    if family not in SUPPORTED_TARGET_FAMILIES:
        supported = ", ".join(sorted(SUPPORTED_TARGET_FAMILIES))
        raise ValueError(f"Unsupported target family {target_family!r}. Expected one of: {supported}.")
    return family


def target_family_spec(target_family: str) -> TargetFamilySpec:
    return SUPPORTED_TARGET_FAMILIES[normalize_target_family(target_family)]


def target_family_for_multipliers(tp_atr: float | int, sl_atr: float | int) -> str | None:
    for family, spec in SUPPORTED_TARGET_FAMILIES.items():
        if float(spec.tp_atr) == float(tp_atr) and float(spec.sl_atr) == float(sl_atr):
            return family
    return None


def supported_target_family_names() -> tuple[str, ...]:
    return tuple(sorted(SUPPORTED_TARGET_FAMILIES))


def preferred_target_family_names() -> tuple[str, ...]:
    return PREFERRED_TARGET_FAMILY_ORDER


def preferred_multiplier_specs() -> tuple[tuple[float, float], ...]:
    return tuple(
        (SUPPORTED_TARGET_FAMILIES[family].tp_atr, SUPPORTED_TARGET_FAMILIES[family].sl_atr)
        for family in PREFERRED_TARGET_FAMILY_ORDER
    )


def triple_barrier_multiplier_specs(*, include_baseline: bool = True) -> tuple[tuple[float, float], ...]:
    preferred_specs = preferred_multiplier_specs()
    return (*BASELINE_TRIPLE_BARRIER_MULTIPLIERS, *preferred_specs) if include_baseline else preferred_specs


def triple_barrier_label_specs(
    directions: tuple[str, ...] = ("long", "short"),
    *,
    include_baseline: bool = True,
) -> tuple[tuple[str, float, float], ...]:
    return tuple(
        (normalize_direction(direction), tp_atr, sl_atr)
        for direction in directions
        for tp_atr, sl_atr in triple_barrier_multiplier_specs(include_baseline=include_baseline)
    )


def family_scoped_root(base_root: Path | str, target_family: str) -> Path:
    """Return an output/input root isolated by target family."""
    root = Path(base_root)
    family = normalize_target_family(target_family)
    return root if root.name == family else root / family


def format_atr_multiplier(value: float | int) -> str:
    """Return a safe ATR multiplier token for column and run names."""
    return f"{float(value):g}".replace(".", "_")


def normalize_direction(direction: str) -> str:
    normalized = str(direction or "").strip().lower()
    if normalized not in {"long", "short"}:
        raise ValueError(f"Unsupported direction {direction!r}. Expected long or short.")
    return normalized


def barrier_stem(direction: str, tp_atr: float | int, sl_atr: float | int) -> str:
    return (
        f"{normalize_direction(direction)}_tp_{format_atr_multiplier(tp_atr)}atr_"
        f"sl_{format_atr_multiplier(sl_atr)}atr"
    )


def barrier_hit_first_column(
    direction: str,
    tp_atr: float | int,
    sl_atr: float | int,
    horizon: int,
) -> str:
    return f"{barrier_stem(direction, tp_atr, sl_atr)}_hit_first_{int(horizon)}"


def barrier_bars_column(
    direction: str,
    tp_atr: float | int,
    sl_atr: float | int,
    horizon: int,
) -> str:
    return f"{barrier_stem(direction, tp_atr, sl_atr)}_bars_to_first_barrier_{int(horizon)}"


def triple_barrier_column(
    direction: str,
    tp_atr: float | int,
    sl_atr: float | int,
    horizon: int,
) -> str:
    return (
        f"{normalize_direction(direction)}_triple_barrier_"
        f"{format_atr_multiplier(tp_atr)}_{format_atr_multiplier(sl_atr)}_{int(horizon)}"
    )


def target_column_for_family(direction: str, target_family: str, horizon: int) -> str:
    spec = target_family_spec(target_family)
    return barrier_hit_first_column(direction, spec.tp_atr, spec.sl_atr, horizon)


def preferred_hit_first_columns(direction: str, horizon: int) -> list[str]:
    return [
        target_column_for_family(direction, family, horizon)
        for family in PREFERRED_TARGET_FAMILY_ORDER
    ]
