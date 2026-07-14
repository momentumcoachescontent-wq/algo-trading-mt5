"""Inspect alternate MT5 CSV files for bars missing from a primary Stage10D dataset.

The command is read-only. It does not patch or merge data. For each explicitly
requested gap it derives the missing timestamps, searches alternate same-symbol
and same-timeframe CSV files, and reports whether replacement evidence is
complete, partial, conflicting, or absent.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.pipeline.inventory_stage10d_phase2_datasets import discover_paths  # noqa: E402
from python.research.stage10d_data_readiness import (  # noqa: E402
    TIMEFRAME_SECONDS,
    load_mt5_csv,
)

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class SourceObservation:
    path: str
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MissingBarEvidence:
    time: str
    sources_found: int
    distinct_values: int
    status: str
    observations: tuple[SourceObservation, ...]


@dataclass(frozen=True)
class GapEvidence:
    previous_time: str
    current_time: str
    missing_bars: int
    status: str
    bars: tuple[MissingBarEvidence, ...]


def _parse_time(value: str) -> datetime:
    try:
        return datetime.strptime(value, _TIME_FORMAT)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported gap timestamp {value!r}; expected YYYY-MM-DD HH:MM:SS"
        ) from exc


def _canonical_time(value: datetime) -> str:
    return value.strftime(_TIME_FORMAT)


def _parse_gap(value: str) -> tuple[datetime, datetime]:
    parts = value.split("|", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid --gap {value!r}; expected 'previous_time|current_time'"
        )
    previous = _parse_time(parts[0].strip())
    current = _parse_time(parts[1].strip())
    if current <= previous:
        raise ValueError("Gap current_time must be later than previous_time")
    return previous, current


def _missing_times(previous: datetime, current: datetime, timeframe: str) -> tuple[datetime, ...]:
    step = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    values: list[datetime] = []
    candidate = previous + step
    while candidate < current:
        values.append(candidate)
        candidate += step
    return tuple(values)


def _row_value(row: dict[str, object]) -> tuple[float, float, float, float, float]:
    return (
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        float(row["volume"]),
    )


def inspect_gap_sources(
    primary: Path,
    roots: Iterable[Path],
    *,
    symbol: str,
    timeframe: str,
    gaps: Iterable[tuple[datetime, datetime]],
) -> dict[str, object]:
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    primary_resolved = primary.resolve()
    if not primary_resolved.exists():
        raise FileNotFoundError(primary_resolved)

    requested_gaps = tuple(gaps)
    if not requested_gaps:
        raise ValueError("At least one --gap is required")

    discovered = discover_paths(roots, symbol=symbol, timeframes=(timeframe,))
    alternate_paths = tuple(
        path for path, discovered_timeframe in discovered
        if discovered_timeframe == timeframe and path.resolve() != primary_resolved
    )

    source_indexes: dict[Path, dict[datetime, dict[str, object]]] = {}
    parse_errors: dict[str, str] = {}
    for path in alternate_paths:
        try:
            rows = load_mt5_csv(path, symbol=symbol, timeframe=timeframe)
        except (OSError, ValueError) as exc:
            parse_errors[str(path)] = str(exc)
            continue
        source_indexes[path] = {row["time"]: row for row in rows}

    gap_evidence: list[GapEvidence] = []
    for previous, current in requested_gaps:
        bar_evidence: list[MissingBarEvidence] = []
        for timestamp in _missing_times(previous, current, timeframe):
            observations: list[SourceObservation] = []
            distinct: set[tuple[float, float, float, float, float]] = set()
            for path, index in source_indexes.items():
                row = index.get(timestamp)
                if row is None:
                    continue
                values = _row_value(row)
                distinct.add(values)
                observations.append(
                    SourceObservation(
                        path=str(path),
                        time=_canonical_time(timestamp),
                        open=values[0],
                        high=values[1],
                        low=values[2],
                        close=values[3],
                        volume=values[4],
                    )
                )
            if not observations:
                status = "MISSING_IN_ALL_ALTERNATE_SOURCES"
            elif len(distinct) > 1:
                status = "CONFLICTING_SOURCE_VALUES"
            else:
                status = "CONSISTENT_SOURCE_VALUE"
            bar_evidence.append(
                MissingBarEvidence(
                    time=_canonical_time(timestamp),
                    sources_found=len(observations),
                    distinct_values=len(distinct),
                    status=status,
                    observations=tuple(sorted(observations, key=lambda item: item.path)),
                )
            )

        statuses = {bar.status for bar in bar_evidence}
        if statuses == {"CONSISTENT_SOURCE_VALUE"}:
            gap_status = "COMPLETE_CONSISTENT_REPAIR_EVIDENCE"
        elif "CONFLICTING_SOURCE_VALUES" in statuses:
            gap_status = "CONFLICTING_REPAIR_EVIDENCE"
        elif "CONSISTENT_SOURCE_VALUE" in statuses:
            gap_status = "PARTIAL_REPAIR_EVIDENCE"
        else:
            gap_status = "NO_REPAIR_EVIDENCE"
        gap_evidence.append(
            GapEvidence(
                previous_time=_canonical_time(previous),
                current_time=_canonical_time(current),
                missing_bars=len(bar_evidence),
                status=gap_status,
                bars=tuple(bar_evidence),
            )
        )

    statuses = {gap.status for gap in gap_evidence}
    if statuses == {"COMPLETE_CONSISTENT_REPAIR_EVIDENCE"}:
        overall = "COMPLETE_CONSISTENT_REPAIR_EVIDENCE"
    elif "CONFLICTING_REPAIR_EVIDENCE" in statuses:
        overall = "CONFLICTING_REPAIR_EVIDENCE"
    elif "PARTIAL_REPAIR_EVIDENCE" in statuses or "COMPLETE_CONSISTENT_REPAIR_EVIDENCE" in statuses:
        overall = "PARTIAL_REPAIR_EVIDENCE"
    else:
        overall = "NO_REPAIR_EVIDENCE"

    return {
        "status": overall,
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "primary": str(primary_resolved),
        "roots": [str(path) for path in roots],
        "alternate_candidates": len(alternate_paths),
        "parseable_alternate_candidates": len(source_indexes),
        "parse_errors": parse_errors,
        "gaps": [asdict(gap) for gap in gap_evidence],
    }


def render_report(report: dict[str, object]) -> str:
    lines = [
        f"Stage10D Phase 2 gap-source inspection: {report['status']}",
        f"Primary: {report['primary']}",
        (
            f"Alternates: candidates={report['alternate_candidates']} "
            f"parseable={report['parseable_alternate_candidates']}"
        ),
    ]
    for gap in report["gaps"]:
        lines.extend(
            (
                "",
                (
                    f"{gap['previous_time']} -> {gap['current_time']} | "
                    f"missing={gap['missing_bars']} | status={gap['status']}"
                ),
            )
        )
        for bar in gap["bars"]:
            lines.append(
                f"  {bar['time']} | status={bar['status']} "
                f"sources={bar['sources_found']} distinct={bar['distinct_values']}"
            )
            for observation in bar["observations"]:
                lines.append(
                    "    "
                    f"{observation['path']} | "
                    f"O={observation['open']} H={observation['high']} "
                    f"L={observation['low']} C={observation['close']} "
                    f"V={observation['volume']}"
                )
    if report["parse_errors"]:
        lines.extend(("", "Parse errors:"))
        for path, error in sorted(report["parse_errors"].items()):
            lines.append(f"  {path}: {error}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary", type=Path)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--timeframe", required=True, choices=tuple(TIMEFRAME_SECONDS))
    parser.add_argument(
        "--gap",
        action="append",
        required=True,
        help="Repeatable 'previous_time|current_time' pair",
    )
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = inspect_gap_sources(
            args.primary,
            args.roots,
            symbol=args.symbol,
            timeframe=args.timeframe,
            gaps=tuple(_parse_gap(value) for value in args.gap),
        )
    except (OSError, ValueError) as exc:
        print(f"Gap-source inspection error: {exc}", file=sys.stderr)
        return 1

    print(render_report(report))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"JSON: {args.json_out}")

    return 0 if report["status"] == "COMPLETE_CONSISTENT_REPAIR_EVIDENCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
