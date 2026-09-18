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
        raw_text = manual_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DailyLadderValidationError(
            f"manual Avo ladder file is unreadable: {manual_path}: {exc}"
        ) from exc
    try:
        payload = json.loads(raw_text)
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

def build_auto_composite_execution_ladder(
    *,
    symbol: str,
    broker_date: date,
    previous_open: float,
    previous_high: float,
    previous_low: float,
    previous_close: float,
    current_open: float,
    pivot_exclusion_range_pct: float = 0.015,
    cluster_range_pct: float = 0.070,
) -> DailyLadder:
    # Build the approved DLLB ladder from existing AUTO composite clusters.
    # Raw family levels and shadow observations remain diagnostic only. DLLB
    # receives only the representative price of each validated composite cluster.
    if not isinstance(broker_date, date) or isinstance(broker_date, datetime):
        raise DailyLadderValidationError(
            "broker_date must be a datetime.date"
        )

    shadow = build_daily_ladder_shadow(
        previous_open=previous_open,
        previous_high=previous_high,
        previous_low=previous_low,
        previous_close=previous_close,
        current_open=current_open,
        pivot_exclusion_range_pct=pivot_exclusion_range_pct,
        cluster_range_pct=cluster_range_pct,
    )

    upper = [
        float(cluster.representative.price)
        for cluster in shadow.upper
    ]
    lower = [
        float(cluster.representative.price)
        for cluster in shadow.lower
    ]

    if not upper or not lower:
        raise DailyLadderValidationError(
            "AUTO composite ladder requires at least one upper and one lower level"
        )

    validated = validate_manual_avo_ladder(
        {
            "symbol": symbol,
            "broker_date": broker_date.isoformat(),
            "pivot": float(shadow.pivot),
            "upper": upper,
            "lower": lower,
        },
        expected_symbol=symbol,
        expected_broker_date=broker_date,
    )

    return DailyLadder(
        symbol=validated.symbol,
        broker_date=validated.broker_date,
        pivot=validated.pivot,
        upper=validated.upper,
        lower=validated.lower,
        source=AUTO_COMPOSITE_MODE,
    )


AUTO_STRONG_MODE = "AUTO_STRONG_DAILY_LADDER"


def build_auto_strong_execution_ladder(
    *,
    symbol: str,
    broker_date: date,
    previous_open: float,
    previous_high: float,
    previous_low: float,
    previous_close: float,
    current_open: float,
    pivot_exclusion_range_pct: float = 0.015,
    cluster_range_pct: float = 0.070,
    max_pivot_distance_range_pct: float = 0.60,
) -> DailyLadder:
    """Build the strong AUTO ladder used by DLLB execution.

    Selection is intentionally narrow:
    - DeMark X/4 pivot, when it sits on one side of the classic pivot.
    - CAM_CORE representatives whose R/S semantics agree with that side.
    - Multi-family (2+) cluster representatives whose R/S semantics agree.
    - All selected levels must be within max_pivot_distance_range_pct of the
      completed prior-D1 range from the classic pivot.

    The broader AUTO composite shadow remains diagnostic/observation-only.
    """
    if not isinstance(broker_date, date) or isinstance(broker_date, datetime):
        raise DailyLadderValidationError(
            "broker_date must be a datetime.date"
        )

    shadow = build_daily_ladder_shadow(
        previous_open=previous_open,
        previous_high=previous_high,
        previous_low=previous_low,
        previous_close=previous_close,
        current_open=current_open,
        pivot_exclusion_range_pct=pivot_exclusion_range_pct,
        cluster_range_pct=cluster_range_pct,
    )

    try:
        distance_pct = float(max_pivot_distance_range_pct)
    except (TypeError, ValueError) as exc:
        raise DailyLadderValidationError(
            "max_pivot_distance_range_pct must be numeric"
        ) from exc
    if not (0.0 < distance_pct < float("inf")):
        raise DailyLadderValidationError(
            "max_pivot_distance_range_pct must be finite and > 0"
        )

    strong_distance_limit = float(shadow.day_range) * distance_pct
    upper: list[float] = []
    lower: list[float] = []

    for side_name, clusters in (
        ("UPPER", shadow.upper),
        ("LOWER", shadow.lower),
    ):
        for cluster in clusters:
            representative = cluster.representative
            representative_price = float(representative.price)
            pivot_distance = abs(
                representative_price - float(shadow.pivot)
            )
            families = {
                str(member.family)
                for member in cluster.members
            }

            name_upper = str(representative.name).upper()
            side_semantics_ok = (
                (side_name == "UPPER" and ":R" in name_upper)
                or (side_name == "LOWER" and ":S" in name_upper)
            )
            core_or_confluent = (
                str(representative.family) == "CAM_CORE"
                or len(families) >= 2
            )

            if not (
                side_semantics_ok
                and core_or_confluent
                and pivot_distance <= strong_distance_limit
            ):
                continue

            if side_name == "UPPER":
                upper.append(representative_price)
            else:
                lower.append(representative_price)

    previous_open_value = float(previous_open)
    previous_high_value = float(previous_high)
    previous_low_value = float(previous_low)
    previous_close_value = float(previous_close)

    if previous_close_value < previous_open_value:
        demark_x = (
            previous_high_value
            + (2.0 * previous_low_value)
            + previous_close_value
        )
    elif previous_close_value > previous_open_value:
        demark_x = (
            (2.0 * previous_high_value)
            + previous_low_value
            + previous_close_value
        )
    else:
        demark_x = (
            previous_high_value
            + previous_low_value
            + (2.0 * previous_close_value)
        )

    demark_pivot = demark_x / 4.0
    demark_distance = abs(demark_pivot - float(shadow.pivot))

    if demark_distance <= strong_distance_limit:
        if demark_pivot > float(shadow.pivot):
            upper.append(demark_pivot)
        elif demark_pivot < float(shadow.pivot):
            lower.append(demark_pivot)

    upper = sorted(set(float(value) for value in upper))
    lower = sorted(set(float(value) for value in lower), reverse=True)

    if not upper or not lower:
        raise DailyLadderValidationError(
            "AUTO strong ladder requires at least one upper and one lower level"
        )

    validated = validate_manual_avo_ladder(
        {
            "symbol": symbol,
            "broker_date": broker_date.isoformat(),
            "pivot": float(shadow.pivot),
            "upper": upper,
            "lower": lower,
        },
        expected_symbol=symbol,
        expected_broker_date=broker_date,
    )

    return DailyLadder(
        symbol=validated.symbol,
        broker_date=validated.broker_date,
        pivot=validated.pivot,
        upper=validated.upper,
        lower=validated.lower,
        source=AUTO_STRONG_MODE,
    )

def _coerce_mt5_utc_datetime(value: Any) -> datetime:
    """Normalize an MT5 bar-open value to a naive UTC datetime."""
    from datetime import timezone

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = None

    if numeric is not None and abs(numeric) >= 100000000:
        try:
            return datetime.fromtimestamp(
                numeric,
                tz=timezone.utc,
            ).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            pass

    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception as exc:
        raise DailyLadderValidationError(
            f"unable to parse current MT5 D1 time: {value!r}"
        ) from exc


def derive_broker_date_from_current_d1_time(
    value: Any,
) -> date:
    """Recover the broker trading-date label from an MT5 UTC D1 open.

    MetaTrader's Python API returns bar times in UTC.  For the broker-date
    contract used by DLLB, a D1 bar is treated as opening at broker midnight.
    The UTC offset is therefore inferred from that D1 open so the same logic
    follows DST/session-offset changes without consulting the local PC clock.
    """
    from datetime import timedelta

    utc_open = _coerce_mt5_utc_datetime(value)

    if utc_open.second != 0 or utc_open.microsecond != 0:
        raise DailyLadderValidationError(
            f"current MT5 D1 open is not minute-aligned: {utc_open!r}"
        )

    minute_of_day = utc_open.hour * 60 + utc_open.minute
    offset_minutes = (-minute_of_day) % (24 * 60)

    # Use the civil-time equivalent inside the normal UTC-offset envelope
    # [-12:00, +14:00].  Example: 21:00 UTC -> +03:00 broker midnight.
    if offset_minutes > 14 * 60:
        offset_minutes -= 24 * 60

    if not (-12 * 60 <= offset_minutes <= 14 * 60):
        raise DailyLadderValidationError(
            "unable to infer plausible broker UTC offset from current D1 open: "
            f"{utc_open!r}"
        )

    broker_midnight = utc_open + timedelta(minutes=offset_minutes)
    if (
        broker_midnight.hour != 0
        or broker_midnight.minute != 0
        or broker_midnight.second != 0
        or broker_midnight.microsecond != 0
    ):
        raise DailyLadderValidationError(
            f"unable to reconstruct broker midnight from current D1 open: {utc_open!r}"
        )

    return broker_midnight.date()


def build_shadow_observations(
    *,
    approved_ladder: DailyLadder,
    raw_levels: Iterable[ShadowLevel],
    cluster_distance: float,
) -> tuple[dict[str, Any], ...]:
    """Classify raw pivot-family levels without giving them execution authority."""
    threshold = max(0.0, float(cluster_distance))

    approved_points: list[tuple[str, float]] = [
        ("APPROVED_PIVOT", float(approved_ladder.pivot)),
    ]
    approved_points.extend(
        (f"APPROVED_UPPER_{index}", float(price))
        for index, price in enumerate(approved_ladder.upper, start=1)
    )
    approved_points.extend(
        (f"APPROVED_LOWER_{index}", float(price))
        for index, price in enumerate(approved_ladder.lower, start=1)
    )

    observations: list[dict[str, Any]] = []

    for raw in raw_levels:
        raw_price = float(raw.price)
        nearest_name, nearest_price = min(
            approved_points,
            key=lambda item: abs(raw_price - item[1]),
        )
        distance = abs(raw_price - nearest_price)

        if distance <= 1e-6:
            classification = "APPROVED"
        elif distance <= threshold:
            classification = "CLUSTERED_WITH_APPROVED"
        else:
            classification = "EXTRA_RAW"

        if raw_price > float(approved_ladder.pivot):
            side = "ABOVE_PIVOT"
        elif raw_price < float(approved_ladder.pivot):
            side = "BELOW_PIVOT"
        else:
            side = "AT_PIVOT"

        observations.append(
            {
                "family": str(raw.family),
                "name": str(raw.name),
                "price": raw_price,
                "side": side,
                "classification": classification,
                "nearest_approved_name": nearest_name,
                "nearest_approved_price": nearest_price,
                "distance_to_nearest_approved": distance,
                "reaction_status": "UNOBSERVED",
                "execution_authority": False,
            }
        )

    return tuple(observations)
