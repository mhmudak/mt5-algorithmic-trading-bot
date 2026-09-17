from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Iterable

AUTO_COMPOSITE_MODE = "AUTO_COMPOSITE_DAILY_LADDER"
MANUAL_AVO_MODE = "MANUAL_AVO_DAILY_LADDER"


class DailyLadderValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DailyLadder:
    symbol: str
    broker_date: date
    pivot: float
    upper: tuple[float, ...]
    lower: tuple[float, ...]
    source: str


@dataclass(frozen=True)
class ShadowLevel:
    family: str
    name: str
    price: float


@dataclass(frozen=True)
class ShadowCluster:
    representative: ShadowLevel
    members: tuple[ShadowLevel, ...]
    low: float
    high: float


@dataclass(frozen=True)
class DailyLadderShadow:
    pivot: float
    day_range: float
    pivot_exclusion: float
    cluster_tolerance: float
    upper: tuple[ShadowCluster, ...]
    lower: tuple[ShadowCluster, ...]


FAMILY_PRIORITY = {
    "CAM_CORE": 0,
    "CLASSIC": 1,
    "CAM_OUTER": 2,
    "FIB": 3,
    "WOODIE": 4,
    "DM": 5,
}


def _as_price(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise DailyLadderValidationError(f"{field} must be a numeric price")
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise DailyLadderValidationError(
            f"{field} must be a numeric price"
        ) from exc
    if price <= 0.0:
        raise DailyLadderValidationError(f"{field} must be > 0")
    return price


def _parse_broker_date(value: Any) -> date:
    if not isinstance(value, str):
        raise DailyLadderValidationError("broker_date must be YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise DailyLadderValidationError(
            "broker_date must be YYYY-MM-DD"
        ) from exc


def _as_price_tuple(value: Any, *, field: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise DailyLadderValidationError(
            f"{field} must be a non-empty list"
        )
    result = tuple(
        _as_price(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise DailyLadderValidationError(
            f"{field} contains duplicate prices"
        )
    return result


def validate_manual_avo_ladder(
    payload: dict[str, Any],
    *,
    expected_symbol: str | None = None,
    expected_broker_date: date | None = None,
) -> DailyLadder:
    if not isinstance(payload, dict):
        raise DailyLadderValidationError(
            "manual Avo ladder payload must be an object"
        )

    symbol_raw = payload.get("symbol")
    if not isinstance(symbol_raw, str) or not symbol_raw.strip():
        raise DailyLadderValidationError(
            "symbol must be a non-empty string"
        )

    symbol = symbol_raw.strip().upper()
    if (
        expected_symbol is not None
        and symbol != expected_symbol.strip().upper()
    ):
        raise DailyLadderValidationError(
            f"symbol mismatch: expected {expected_symbol}, got {symbol}"
        )

    broker_date = _parse_broker_date(payload.get("broker_date"))
    if (
        expected_broker_date is not None
        and broker_date != expected_broker_date
    ):
        raise DailyLadderValidationError(
            "stale/future manual Avo ladder: "
            f"expected broker_date={expected_broker_date.isoformat()}, "
            f"got {broker_date.isoformat()}"
        )

    pivot = _as_price(payload.get("pivot"), field="pivot")
    upper = _as_price_tuple(payload.get("upper"), field="upper")
    lower = _as_price_tuple(payload.get("lower"), field="lower")

    if tuple(sorted(upper)) != upper:
        raise DailyLadderValidationError(
            "upper must be strictly ordered nearest-to-farthest ascending"
        )
    if tuple(sorted(lower, reverse=True)) != lower:
        raise DailyLadderValidationError(
            "lower must be strictly ordered nearest-to-farthest descending"
        )
    if any(level <= pivot for level in upper):
        raise DailyLadderValidationError(
            "every upper level must be above pivot"
        )
    if any(level >= pivot for level in lower):
        raise DailyLadderValidationError(
            "every lower level must be below pivot"
        )
    if len(set(lower + (pivot,) + upper)) != (
        len(lower) + 1 + len(upper)
    ):
        raise DailyLadderValidationError(
            "pivot/upper/lower prices must all be unique"
        )

    return DailyLadder(
        symbol=symbol,
        broker_date=broker_date,
        pivot=pivot,
        upper=upper,
        lower=lower,
        source=MANUAL_AVO_MODE,
    )


validate_manual_daily_ladder = validate_manual_avo_ladder


def load_manual_avo_ladder(
    path: str | Path,
    *,
    expected_symbol: str | None = None,
    expected_broker_date: date | None = None,
) -> DailyLadder:
    manual_path = Path(path)
    if not manual_path.exists():
        raise DailyLadderValidationError(
            f"manual Avo ladder file does not exist: {manual_path}"
        )
    try:
        payload = json.loads(
            manual_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise DailyLadderValidationError(
            f"manual Avo ladder JSON is invalid: {manual_path}"
        ) from exc
    return validate_manual_avo_ladder(
        payload,
        expected_symbol=expected_symbol,
        expected_broker_date=expected_broker_date,
    )


load_manual_daily_ladder = load_manual_avo_ladder


def _add(
    out: list[ShadowLevel],
    family: str,
    name: str,
    price: float,
) -> None:
    out.append(
        ShadowLevel(
            family=family,
            name=name,
            price=float(price),
        )
    )


def calculate_shadow_levels(
    *,
    previous_open: float,
    previous_high: float,
    previous_low: float,
    previous_close: float,
    current_open: float,
) -> tuple[float, tuple[ShadowLevel, ...]]:
    h = float(previous_high)
    l = float(previous_low)
    c = float(previous_close)
    o = float(previous_open)
    current_o = float(current_open)

    if h <= l:
        raise DailyLadderValidationError(
            "previous D1 high must be above low"
        )

    day_range = h - l
    pivot = (h + l + c) / 3.0
    levels: list[ShadowLevel] = []

    for index, factor in (
        (1, 1.1 / 12.0),
        (2, 1.1 / 6.0),
        (3, 1.1 / 4.0),
    ):
        _add(
            levels,
            "CAM_CORE",
            f"CAM:R{index}",
            c + day_range * factor,
        )
        _add(
            levels,
            "CAM_CORE",
            f"CAM:S{index}",
            c - day_range * factor,
        )

    _add(levels, "CLASSIC", "CLASSIC:R1", 2.0 * pivot - l)
    _add(levels, "CLASSIC", "CLASSIC:S1", 2.0 * pivot - h)
    _add(levels, "CLASSIC", "CLASSIC:R2", pivot + day_range)
    _add(levels, "CLASSIC", "CLASSIC:S2", pivot - day_range)

    _add(
        levels,
        "CAM_OUTER",
        "CAM:R4",
        c + day_range * (1.1 / 2.0),
    )
    _add(
        levels,
        "CAM_OUTER",
        "CAM:S4",
        c - day_range * (1.1 / 2.0),
    )

    if l != 0.0:
        cam_r5 = (h / l) * c
        cam_s5 = c - (cam_r5 - c)
        _add(levels, "CAM_OUTER", "CAM:R5", cam_r5)
        _add(levels, "CAM_OUTER", "CAM:S5", cam_s5)

    for index, factor in ((1, 0.382), (2, 0.618)):
        _add(
            levels,
            "FIB",
            f"FIB:R{index}",
            pivot + factor * day_range,
        )
        _add(
            levels,
            "FIB",
            f"FIB:S{index}",
            pivot - factor * day_range,
        )

    woodie_pivot = (
        h
        + l
        + 2.0 * current_o
    ) / 4.0

    _add(
        levels,
        "WOODIE",
        "WOODIE:R1",
        2.0 * woodie_pivot - l,
    )
    _add(
        levels,
        "WOODIE",
        "WOODIE:S1",
        2.0 * woodie_pivot - h,
    )
    _add(
        levels,
        "WOODIE",
        "WOODIE:R2",
        woodie_pivot + day_range,
    )
    _add(
        levels,
        "WOODIE",
        "WOODIE:S2",
        woodie_pivot - day_range,
    )

    if o == c:
        x = h + l + 2.0 * c
    elif c > o:
        x = 2.0 * h + l + c
    else:
        x = 2.0 * l + h + c

    _add(levels, "DM", "DM:R1", x / 2.0 - l)
    _add(levels, "DM", "DM:S1", x / 2.0 - h)

    return pivot, tuple(levels)


def _median(values: Iterable[float]) -> float:
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (
        ordered[middle - 1]
        + ordered[middle]
    ) / 2.0


def _cluster(
    levels: Iterable[ShadowLevel],
    *,
    tolerance: float,
) -> tuple[tuple[ShadowLevel, ...], ...]:
    ordered = sorted(
        levels,
        key=lambda item: (
            item.price,
            FAMILY_PRIORITY.get(item.family, 99),
            item.name,
        ),
    )
    clusters: list[list[ShadowLevel]] = []

    for level in ordered:
        if not clusters:
            clusters.append([level])
            continue

        active = clusters[-1]
        prices = [item.price for item in active]

        if (
            max(max(prices), level.price)
            - min(min(prices), level.price)
            <= tolerance
        ):
            active.append(level)
        else:
            clusters.append([level])

    return tuple(
        tuple(cluster)
        for cluster in clusters
    )


def _representative(
    cluster: tuple[ShadowLevel, ...],
) -> ShadowLevel:
    middle = _median(
        item.price
        for item in cluster
    )
    return min(
        cluster,
        key=lambda item: (
            FAMILY_PRIORITY.get(item.family, 99),
            abs(item.price - middle),
            item.name,
        ),
    )


def build_daily_ladder_shadow(
    *,
    previous_open: float,
    previous_high: float,
    previous_low: float,
    previous_close: float,
    current_open: float,
    pivot_exclusion_range_pct: float = 0.015,
    cluster_range_pct: float = 0.070,
) -> DailyLadderShadow:
    pivot, raw_levels = calculate_shadow_levels(
        previous_open=previous_open,
        previous_high=previous_high,
        previous_low=previous_low,
        previous_close=previous_close,
        current_open=current_open,
    )

    day_range = (
        float(previous_high)
        - float(previous_low)
    )
    pivot_exclusion = (
        day_range
        * float(pivot_exclusion_range_pct)
    )
    cluster_tolerance = (
        day_range
        * float(cluster_range_pct)
    )

    filtered = tuple(
        item
        for item in raw_levels
        if abs(item.price - pivot) >= pivot_exclusion
    )

    upper: list[ShadowCluster] = []
    lower: list[ShadowCluster] = []

    for cluster in _cluster(
        filtered,
        tolerance=cluster_tolerance,
    ):
        rep = _representative(cluster)
        prices = tuple(
            item.price
            for item in cluster
        )
        row = ShadowCluster(
            representative=rep,
            members=cluster,
            low=min(prices),
            high=max(prices),
        )
        if rep.price > pivot:
            upper.append(row)
        elif rep.price < pivot:
            lower.append(row)

    upper.sort(
        key=lambda row: row.representative.price
    )
    lower.sort(
        key=lambda row: row.representative.price,
        reverse=True,
    )

    return DailyLadderShadow(
        pivot=pivot,
        day_range=day_range,
        pivot_exclusion=pivot_exclusion,
        cluster_tolerance=cluster_tolerance,
        upper=tuple(upper),
        lower=tuple(lower),
    )


def auto_composite_display_levels(
    *,
    previous_open: float,
    previous_high: float,
    previous_low: float,
    previous_close: float,
    current_open: float,
    pivot_exclusion_range_pct: float = 0.015,
    cluster_range_pct: float = 0.070,
) -> DailyLadderShadow:
    """Observation/display context only. Never an execution ladder."""
    return build_daily_ladder_shadow(
        previous_open=previous_open,
        previous_high=previous_high,
        previous_low=previous_low,
        previous_close=previous_close,
        current_open=current_open,
        pivot_exclusion_range_pct=pivot_exclusion_range_pct,
        cluster_range_pct=cluster_range_pct,
    )
