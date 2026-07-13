"""Stage10D Phase 2 canonical MT5 CSV readiness contract.

This module intentionally uses only the Python standard library so the data gate
can run in CI and on the MT5 host without adding research dependencies.  It
preserves broker-server timestamps as naive wall-clock values; timezone metadata
is mandatory and no silent UTC conversion is performed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Optional

PARSER_VERSION = "stage10d-phase2-csv-v1"
MANIFEST_VERSION = "stage10d-data-manifest-v1"

TIMEFRAME_SECONDS = {
    "M15": 15 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
    "D1": 24 * 60 * 60,
}

_TIME_FORMATS = (
    "%Y.%m.%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M",
)


@dataclass(frozen=True)
class GapRecord:
    previous_time: str
    current_time: str
    delta_seconds: int
    missing_bars: int
    classification: str


@dataclass(frozen=True)
class QualityReport:
    row_count: int
    unique_row_count: int
    duplicate_count: int
    ohlc_violation_count: int
    nonpositive_volume_count: int
    expected_market_closure_gap_count: int
    broker_session_gap_count: int
    missing_export_segment_gap_count: int
    unknown_gap_count: int
    gaps: tuple[GapRecord, ...]
    status: str


@dataclass(frozen=True)
class DatasetManifest:
    manifest_version: str
    data_manifest_id: str
    parser_version: str
    generated_at_utc: str
    source_file: str
    source_sha256: str
    source_size_bytes: int
    broker: str
    terminal: str
    symbol: str
    timeframe: str
    server_timezone: str
    export_timestamp_utc: Optional[str]
    synthetic: bool
    row_count: int
    first_bar_time: Optional[str]
    last_bar_time: Optional[str]
    quality_status: str
    duplicate_count: int
    ohlc_violation_count: int
    nonpositive_volume_count: int
    expected_market_closure_gap_count: int
    broker_session_gap_count: int
    missing_export_segment_gap_count: int
    unknown_gap_count: int


@dataclass(frozen=True)
class ReadinessBundle:
    rows: tuple[dict[str, object], ...]
    quality: QualityReport
    manifest: DatasetManifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace("<", "").replace(">", "")


def _parse_time(value: str) -> datetime:
    cleaned = value.strip().replace("T", " ")
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"Unsupported MT5 timestamp: {value!r}") from exc
    if parsed.tzinfo is not None:
        raise ValueError(
            "Timezone-aware timestamps are not accepted in canonical MT5 CSV input; "
            "provide broker-server wall-clock time plus --server-timezone metadata."
        )
    return parsed


def _detect_delimiter(sample: str) -> str:
    candidates = ("\t", ",", ";")
    counts = {candidate: sample.count(candidate) for candidate in candidates}
    delimiter = max(counts, key=counts.get)
    if counts[delimiter] == 0:
        raise ValueError("Unable to detect CSV delimiter; expected tab, comma or semicolon.")
    return delimiter


def _canonical_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def load_mt5_csv(path: Path, symbol: str, timeframe: str) -> tuple[dict[str, object], ...]:
    """Load and normalize an MT5 OHLCV export without timezone conversion."""

    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if not symbol.strip():
        raise ValueError("symbol is required")

    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError(f"CSV is empty: {path}")

    delimiter = _detect_delimiter(text.splitlines()[0])
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError("CSV header is missing")

    normalized_fields = {_normalize_header(name): name for name in reader.fieldnames}
    required_prices = ("open", "high", "low", "close")
    missing_prices = [name for name in required_prices if name not in normalized_fields]
    if missing_prices:
        raise ValueError(f"Missing required columns: {', '.join(missing_prices)}")

    volume_key = "tick_volume" if "tick_volume" in normalized_fields else "volume"
    if volume_key not in normalized_fields:
        raise ValueError("Missing required volume/tick_volume column")

    has_combined_time = "time" in normalized_fields
    has_split_time = "date" in normalized_fields and "time" in normalized_fields
    if not has_combined_time:
        raise ValueError("Missing time column")

    rows: list[dict[str, object]] = []
    for line_number, source_row in enumerate(reader, start=2):
        normalized = {
            _normalize_header(key): (value or "").strip()
            for key, value in source_row.items()
            if key is not None
        }
        try:
            if has_split_time and normalized.get("date"):
                timestamp_text = f"{normalized['date']} {normalized['time']}"
            else:
                timestamp_text = normalized["time"]
            timestamp = _parse_time(timestamp_text)
            row = {
                "time": timestamp,
                "open": float(normalized["open"]),
                "high": float(normalized["high"]),
                "low": float(normalized["low"]),
                "close": float(normalized["close"]),
                "volume": float(normalized[volume_key]),
                "symbol": symbol.upper(),
                "timeframe": timeframe,
            }
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Invalid row {line_number}: {exc}") from exc
        rows.append(row)

    if not rows:
        raise ValueError("CSV contains no data rows")
    return tuple(rows)


def _missing_timestamps(previous: datetime, current: datetime, step: timedelta) -> list[datetime]:
    result: list[datetime] = []
    candidate = previous + step
    while candidate < current:
        result.append(candidate)
        candidate += step
    return result


def _classify_gap(previous: datetime, current: datetime, expected_seconds: int) -> GapRecord:
    delta_seconds = int((current - previous).total_seconds())
    if delta_seconds <= expected_seconds or delta_seconds % expected_seconds != 0:
        return GapRecord(
            previous_time=_canonical_time(previous),
            current_time=_canonical_time(current),
            delta_seconds=delta_seconds,
            missing_bars=max(0, delta_seconds // expected_seconds - 1),
            classification="unknown_gap",
        )

    missing = _missing_timestamps(previous, current, timedelta(seconds=expected_seconds))
    classification = (
        "expected_market_closure"
        if missing and all(timestamp.weekday() >= 5 for timestamp in missing)
        else "missing_export_segment"
    )
    return GapRecord(
        previous_time=_canonical_time(previous),
        current_time=_canonical_time(current),
        delta_seconds=delta_seconds,
        missing_bars=len(missing),
        classification=classification,
    )


def audit_rows(rows: Iterable[Mapping[str, object]], timeframe: str) -> QualityReport:
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    materialized = list(rows)
    times = [row["time"] for row in materialized]
    if not all(isinstance(value, datetime) for value in times):
        raise ValueError("All rows must contain datetime values in 'time'")

    duplicate_count = len(times) - len(set(times))
    unique_by_time: dict[datetime, Mapping[str, object]] = {}
    for row in materialized:
        unique_by_time.setdefault(row["time"], row)  # first occurrence is canonical
    ordered = [unique_by_time[key] for key in sorted(unique_by_time)]

    ohlc_violations = 0
    nonpositive_volume = 0
    for row in ordered:
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"])
        if high < max(open_price, close) or low > min(open_price, close) or high < low:
            ohlc_violations += 1
        if volume <= 0:
            nonpositive_volume += 1

    expected_seconds = TIMEFRAME_SECONDS[timeframe]
    gaps: list[GapRecord] = []
    for previous, current in zip(ordered, ordered[1:]):
        previous_time = previous["time"]
        current_time = current["time"]
        delta_seconds = int((current_time - previous_time).total_seconds())
        if delta_seconds != expected_seconds:
            gaps.append(_classify_gap(previous_time, current_time, expected_seconds))

    counts = {
        classification: sum(gap.classification == classification for gap in gaps)
        for classification in (
            "expected_market_closure",
            "broker_session_gap",
            "missing_export_segment",
            "unknown_gap",
        )
    }
    failed = any(
        (
            duplicate_count,
            ohlc_violations,
            nonpositive_volume,
            counts["missing_export_segment"],
            counts["unknown_gap"],
        )
    )
    return QualityReport(
        row_count=len(materialized),
        unique_row_count=len(ordered),
        duplicate_count=duplicate_count,
        ohlc_violation_count=ohlc_violations,
        nonpositive_volume_count=nonpositive_volume,
        expected_market_closure_gap_count=counts["expected_market_closure"],
        broker_session_gap_count=counts["broker_session_gap"],
        missing_export_segment_gap_count=counts["missing_export_segment"],
        unknown_gap_count=counts["unknown_gap"],
        gaps=tuple(gaps),
        status="FAIL" if failed else "PASS",
    )


def _manifest_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def build_readiness_bundle(
    path: Path,
    *,
    symbol: str,
    timeframe: str,
    broker: str,
    terminal: str,
    server_timezone: str,
    export_timestamp_utc: Optional[str] = None,
) -> ReadinessBundle:
    for name, value in {
        "broker": broker,
        "terminal": terminal,
        "server_timezone": server_timezone,
    }.items():
        if not value.strip():
            raise ValueError(f"{name} is required")

    rows = load_mt5_csv(path, symbol=symbol, timeframe=timeframe)
    quality = audit_rows(rows, timeframe=timeframe)
    ordered_times = sorted(row["time"] for row in rows)
    source_hash = sha256_file(path)
    identity = {
        "manifest_version": MANIFEST_VERSION,
        "parser_version": PARSER_VERSION,
        "source_sha256": source_hash,
        "broker": broker,
        "terminal": terminal,
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "server_timezone": server_timezone,
        "export_timestamp_utc": export_timestamp_utc,
        "synthetic": False,
    }
    manifest = DatasetManifest(
        manifest_version=MANIFEST_VERSION,
        data_manifest_id=_manifest_id(identity),
        parser_version=PARSER_VERSION,
        generated_at_utc=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        source_file=str(path),
        source_sha256=source_hash,
        source_size_bytes=path.stat().st_size,
        broker=broker,
        terminal=terminal,
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        server_timezone=server_timezone,
        export_timestamp_utc=export_timestamp_utc,
        synthetic=False,
        row_count=len(rows),
        first_bar_time=_canonical_time(ordered_times[0]) if ordered_times else None,
        last_bar_time=_canonical_time(ordered_times[-1]) if ordered_times else None,
        quality_status=quality.status,
        duplicate_count=quality.duplicate_count,
        ohlc_violation_count=quality.ohlc_violation_count,
        nonpositive_volume_count=quality.nonpositive_volume_count,
        expected_market_closure_gap_count=quality.expected_market_closure_gap_count,
        broker_session_gap_count=quality.broker_session_gap_count,
        missing_export_segment_gap_count=quality.missing_export_segment_gap_count,
        unknown_gap_count=quality.unknown_gap_count,
    )
    return ReadinessBundle(rows=rows, quality=quality, manifest=manifest)


def write_bundle(bundle: ReadinessBundle, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{bundle.manifest.symbol.lower()}_{bundle.manifest.timeframe.lower()}_"
        f"{bundle.manifest.data_manifest_id}"
    )
    manifest_path = output_dir / f"{stem}_manifest.json"
    quality_path = output_dir / f"{stem}_quality.json"
    normalized_path = output_dir / f"{stem}_normalized.csv"

    manifest_path.write_text(
        json.dumps(asdict(bundle.manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps(asdict(bundle.quality), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with normalized_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("time", "open", "high", "low", "close", "volume", "symbol", "timeframe"),
        )
        writer.writeheader()
        for row in sorted(bundle.rows, key=lambda item: item["time"]):
            rendered = dict(row)
            rendered["time"] = _canonical_time(rendered["time"])
            writer.writerow(rendered)

    return {
        "manifest": manifest_path,
        "quality": quality_path,
        "normalized": normalized_path,
    }
