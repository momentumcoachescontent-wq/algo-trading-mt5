"""Build Stage10D directional EMA21 touch-gap features from governed H4 data.

The implementation is deliberately standard-library only.  It uses completed bars,
never reads future rows, preserves broker-server wall-clock timestamps, and resets
indicator state after governed missing-bar intervals.  Confirmed market/session
closures do not reset the indicator state because no synthetic trading bars are
expected inside those intervals.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Optional

from python.research.stage10d_data_readiness import load_mt5_csv, sha256_file

TOUCH_FEATURE_VERSION = "stage10d-touch-features-v1"
DEFAULT_EMA_PERIOD = 21
DEFAULT_ATR_PERIOD = 14
DEFAULT_EXACT_ATR = 0.25
DEFAULT_SOFT_ATR = 0.50
DEFAULT_EXTENDED_ATR = 1.50


@dataclass(frozen=True)
class TouchThresholds:
    exact_atr: float = DEFAULT_EXACT_ATR
    soft_atr: float = DEFAULT_SOFT_ATR
    extended_atr: float = DEFAULT_EXTENDED_ATR

    def validate(self) -> None:
        if self.exact_atr < 0:
            raise ValueError("exact_atr must be non-negative")
        if not self.exact_atr <= self.soft_atr <= self.extended_atr:
            raise ValueError("touch thresholds must satisfy exact <= soft <= extended")


@dataclass(frozen=True)
class TouchFeatureArtifact:
    feature_version: str
    feature_artifact_id: str
    generated_at_utc: str
    governed_manifest_id: str
    source_sha256: str
    symbol: str
    timeframe: str
    row_count: int
    eligible_row_count: int
    ineligible_row_count: int
    first_bar_time: str
    last_bar_time: str
    ema_period: int
    atr_period: int
    exact_atr: float
    soft_atr: float
    extended_atr: float
    excluded_bar_times: tuple[str, ...]
    segment_reset_count: int
    no_lookahead_contract: str
    synthetic: bool


def _canonical_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_canonical_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _artifact_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _classify_gap(value: Optional[float], thresholds: TouchThresholds) -> str:
    if value is None:
        return "unknown"
    if value <= thresholds.exact_atr:
        return "inside_exact"
    if value <= thresholds.soft_atr:
        return "outside_exact_inside_soft"
    if value <= thresholds.extended_atr:
        return "outside_soft_inside_extended"
    return "outside_extended"


def _crosses_excluded_timestamp(
    previous: datetime,
    current: datetime,
    excluded: set[datetime],
) -> bool:
    return any(previous < value < current for value in excluded)


def _touch_side(
    *,
    direction: str,
    high: float,
    low: float,
    ema: Optional[float],
    atr: Optional[float],
    indicators_valid: bool,
    thresholds: TouchThresholds,
) -> dict[str, object]:
    prefix = direction.lower()
    result: dict[str, object] = {
        f"touch_gap_{prefix}_price": None,
        f"touch_gap_{prefix}_atr": None,
        f"touch_class_{prefix}": "unknown",
        f"geometric_contact_{prefix}": None,
        f"touch_zone_exact_{prefix}": None,
        f"touch_zone_soft_{prefix}": None,
        f"touch_zone_extended_{prefix}": None,
    }
    if not indicators_valid or ema is None or atr is None or atr <= 0:
        return result

    if direction == "BUY":
        directionally_defined = high >= ema
        gap_price = max(0.0, low - ema) if directionally_defined else None
    elif direction == "SELL":
        directionally_defined = low <= ema
        gap_price = max(0.0, ema - high) if directionally_defined else None
    else:
        raise ValueError(f"Unsupported direction: {direction}")

    if gap_price is None:
        return result

    gap_atr = gap_price / atr
    result.update(
        {
            f"touch_gap_{prefix}_price": gap_price,
            f"touch_gap_{prefix}_atr": gap_atr,
            f"touch_class_{prefix}": _classify_gap(gap_atr, thresholds),
            f"geometric_contact_{prefix}": gap_price == 0.0,
            f"touch_zone_exact_{prefix}": gap_atr <= thresholds.exact_atr,
            f"touch_zone_soft_{prefix}": gap_atr <= thresholds.soft_atr,
            f"touch_zone_extended_{prefix}": gap_atr <= thresholds.extended_atr,
        }
    )
    return result


def build_touch_features(
    rows: Iterable[Mapping[str, object]],
    *,
    excluded_bar_times: Iterable[str] = (),
    ema_period: int = DEFAULT_EMA_PERIOD,
    atr_period: int = DEFAULT_ATR_PERIOD,
    thresholds: TouchThresholds = TouchThresholds(),
) -> tuple[dict[str, object], ...]:
    """Return deterministic closed-bar touch features with no future-row access."""

    thresholds.validate()
    if ema_period < 2:
        raise ValueError("ema_period must be at least 2")
    if atr_period < 1:
        raise ValueError("atr_period must be positive")

    ordered = sorted((dict(row) for row in rows), key=lambda item: item["time"])
    if not ordered:
        raise ValueError("rows must not be empty")
    if len({row["time"] for row in ordered}) != len(ordered):
        raise ValueError("touch feature input contains duplicate timestamps")

    excluded = {_parse_canonical_time(value) for value in excluded_bar_times}
    alpha = 2.0 / (ema_period + 1.0)

    output: list[dict[str, object]] = []
    segment_closes: list[float] = []
    segment_true_ranges: list[float] = []
    ema_value: Optional[float] = None
    atr_value: Optional[float] = None
    previous_close: Optional[float] = None
    previous_time: Optional[datetime] = None
    segment_id = 0

    for row in ordered:
        current_time = row["time"]
        if not isinstance(current_time, datetime):
            raise ValueError("row time must be datetime")

        reset_reason: Optional[str] = None
        if previous_time is not None and _crosses_excluded_timestamp(previous_time, current_time, excluded):
            segment_id += 1
            segment_closes = []
            segment_true_ranges = []
            ema_value = None
            atr_value = None
            previous_close = None
            reset_reason = "governed_data_gap"

        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        segment_closes.append(close)
        if ema_value is None:
            if len(segment_closes) == ema_period:
                ema_value = sum(segment_closes) / ema_period
        else:
            ema_value = alpha * close + (1.0 - alpha) * ema_value

        if previous_close is not None:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
            segment_true_ranges.append(true_range)
            if atr_value is None:
                if len(segment_true_ranges) == atr_period:
                    atr_value = sum(segment_true_ranges) / atr_period
            else:
                atr_value = ((atr_period - 1.0) * atr_value + true_range) / atr_period

        current_is_excluded = current_time in excluded
        indicators_valid = ema_value is not None and atr_value is not None and not current_is_excluded
        if current_is_excluded:
            eligibility_reason = "excluded_bar_time"
        elif ema_value is None:
            eligibility_reason = "ema_warmup"
        elif atr_value is None:
            eligibility_reason = "atr_warmup"
        else:
            eligibility_reason = "eligible"

        feature = {
            **row,
            "segment_id": segment_id,
            "segment_reset_reason": reset_reason,
            "ema21": ema_value,
            "atr14": atr_value,
            "indicators_valid": indicators_valid,
            "touch_feature_eligible": indicators_valid,
            "touch_feature_eligibility_reason": eligibility_reason,
        }
        feature.update(
            _touch_side(
                direction="BUY",
                high=high,
                low=low,
                ema=ema_value,
                atr=atr_value,
                indicators_valid=indicators_valid,
                thresholds=thresholds,
            )
        )
        feature.update(
            _touch_side(
                direction="SELL",
                high=high,
                low=low,
                ema=ema_value,
                atr=atr_value,
                indicators_valid=indicators_valid,
                thresholds=thresholds,
            )
        )
        output.append(feature)
        previous_close = close
        previous_time = current_time

    return tuple(output)


def load_governed_manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("governed manifest must be a JSON object")
    return payload


def build_touch_artifact(
    csv_path: Path,
    governed_manifest_path: Path,
    *,
    thresholds: TouchThresholds = TouchThresholds(),
    ema_period: int = DEFAULT_EMA_PERIOD,
    atr_period: int = DEFAULT_ATR_PERIOD,
) -> tuple[TouchFeatureArtifact, tuple[dict[str, object], ...]]:
    manifest = load_governed_manifest(governed_manifest_path)
    if manifest.get("research_eligible") is not True:
        raise ValueError("governed manifest is not research eligible")
    if str(manifest.get("timeframe", "")).upper() != "H4":
        raise ValueError("directional touch features currently require an H4 governed manifest")

    observed_hash = sha256_file(csv_path)
    if observed_hash != manifest.get("source_sha256"):
        raise ValueError("source CSV checksum does not match governed manifest")

    symbol = str(manifest.get("symbol", "")).upper()
    rows = load_mt5_csv(csv_path, symbol=symbol, timeframe="H4")
    excluded = tuple(str(value) for value in manifest.get("excluded_bar_times", []))
    features = build_touch_features(
        rows,
        excluded_bar_times=excluded,
        ema_period=ema_period,
        atr_period=atr_period,
        thresholds=thresholds,
    )
    identity = {
        "feature_version": TOUCH_FEATURE_VERSION,
        "governed_manifest_id": manifest.get("governed_manifest_id"),
        "source_sha256": observed_hash,
        "ema_period": ema_period,
        "atr_period": atr_period,
        "exact_atr": thresholds.exact_atr,
        "soft_atr": thresholds.soft_atr,
        "extended_atr": thresholds.extended_atr,
        "excluded_bar_times": excluded,
        "synthetic": False,
    }
    eligible_count = sum(bool(row["touch_feature_eligible"]) for row in features)
    artifact = TouchFeatureArtifact(
        feature_version=TOUCH_FEATURE_VERSION,
        feature_artifact_id=_artifact_id(identity),
        generated_at_utc=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        governed_manifest_id=str(manifest.get("governed_manifest_id", "")),
        source_sha256=observed_hash,
        symbol=symbol,
        timeframe="H4",
        row_count=len(features),
        eligible_row_count=eligible_count,
        ineligible_row_count=len(features) - eligible_count,
        first_bar_time=_canonical_time(features[0]["time"]),
        last_bar_time=_canonical_time(features[-1]["time"]),
        ema_period=ema_period,
        atr_period=atr_period,
        exact_atr=thresholds.exact_atr,
        soft_atr=thresholds.soft_atr,
        extended_atr=thresholds.extended_atr,
        excluded_bar_times=excluded,
        segment_reset_count=sum(row["segment_reset_reason"] is not None for row in features),
        no_lookahead_contract="features at bar t use only rows with time <= t; current evaluated bar is completed",
        synthetic=False,
    )
    return artifact, features


def write_touch_artifact(
    artifact: TouchFeatureArtifact,
    features: Iterable[Mapping[str, object]],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{artifact.symbol.lower()}_h4_{artifact.feature_artifact_id}"
    manifest_path = output_dir / f"{stem}_touch_manifest.json"
    csv_path = output_dir / f"{stem}_touch_features.csv"

    manifest_path.write_text(
        json.dumps(asdict(artifact), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    materialized = list(features)
    fieldnames = list(materialized[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in materialized:
            rendered = dict(row)
            rendered["time"] = _canonical_time(rendered["time"])
            writer.writerow(rendered)
    return {"touch_manifest": manifest_path, "touch_features": csv_path}
