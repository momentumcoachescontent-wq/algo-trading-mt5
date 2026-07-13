"""Inventory local MT5 CSV candidates for Stage10D Phase 2.

The command is read-only. It discovers symbol/timeframe exports, parses them with
the canonical Phase 2 contract, reports quality/range/checksum information and
separates the freshest candidate from the longest-coverage candidate. When those
are different and neither contains the other's range, the report requires a full
re-export or an explicitly governed reconciliation instead of silently choosing a
partial file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.research.stage10d_data_readiness import (  # noqa: E402
    audit_rows,
    load_mt5_csv,
    sha256_file,
)

TIMEFRAME_PATTERN = re.compile(r"(?:^|[_-])(M15|H4|D1)(?=[_.-]|$)", re.IGNORECASE)
SOURCE_PRIORITY = {
    "canonical_archive": 6,
    "direct_export": 5,
    "raw": 4,
    "research_bundle": 3,
    "prepared": 2,
    "copy": 1,
    "other": 0,
}


@dataclass(frozen=True)
class CandidateRecord:
    path: str
    timeframe: str
    source_kind: str
    parse_status: str
    parse_error: Optional[str]
    quality_status: Optional[str]
    row_count: Optional[int]
    first_bar_time: Optional[str]
    last_bar_time: Optional[str]
    coverage_seconds: Optional[int]
    source_sha256: Optional[str]
    source_size_bytes: int
    modified_at_utc: str
    duplicate_count: Optional[int]
    source_order_violation_count: Optional[int]
    ohlc_violation_count: Optional[int]
    nonpositive_volume_count: Optional[int]
    missing_export_segment_gap_count: Optional[int]
    unknown_gap_count: Optional[int]


@dataclass(frozen=True)
class TimeframeSummary:
    timeframe: str
    candidates_total: int
    parseable_candidates: int
    passing_candidates: int
    freshest_candidate: Optional[str]
    longest_coverage_candidate: Optional[str]
    selected_candidate: Optional[str]
    recommended_action: str
    duplicate_sha_groups: tuple[tuple[str, ...], ...]


def _canonical_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_canonical_time(value: Optional[str]) -> datetime:
    if not value:
        return datetime.min
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def infer_timeframe(path: Path) -> Optional[str]:
    matches = {match.upper() for match in TIMEFRAME_PATTERN.findall(path.name)}
    if len(matches) != 1:
        return None
    return next(iter(matches))


def classify_source(path: Path) -> str:
    lowered = str(path).lower().replace("\\", "/")
    if "copia de" in lowered or "/copy" in lowered:
        return "copy"
    if "/data/raw/mt5_exports/" in lowered:
        return "canonical_archive"
    if "/exports/" in lowered:
        return "direct_export"
    if "/data/raw/prepared/" in lowered:
        return "prepared"
    if "/research_bundle/" in lowered:
        return "research_bundle"
    if "/data/raw/" in lowered:
        return "raw"
    return "other"


def discover_paths(
    roots: Iterable[Path],
    *,
    symbol: str,
    timeframes: Iterable[str],
) -> tuple[tuple[Path, str], ...]:
    symbol_upper = symbol.upper()
    allowed = {value.upper() for value in timeframes}
    discovered: dict[Path, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if symbol_upper not in path.name.upper():
                continue
            if path.name.lower().endswith("_normalized.csv"):
                continue
            timeframe = infer_timeframe(path)
            if timeframe is None or timeframe not in allowed:
                continue
            discovered[path.resolve()] = timeframe
    return tuple(sorted(discovered.items(), key=lambda item: str(item[0])))


def inspect_candidate(path: Path, *, symbol: str, timeframe: str) -> CandidateRecord:
    stat = path.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        rows = load_mt5_csv(path, symbol=symbol, timeframe=timeframe)
        quality = audit_rows(rows, timeframe=timeframe)
        times = sorted(row["time"] for row in rows)
        first = times[0]
        last = times[-1]
        return CandidateRecord(
            path=str(path),
            timeframe=timeframe,
            source_kind=classify_source(path),
            parse_status="PASS",
            parse_error=None,
            quality_status=quality.status,
            row_count=len(rows),
            first_bar_time=_canonical_time(first),
            last_bar_time=_canonical_time(last),
            coverage_seconds=int((last - first).total_seconds()),
            source_sha256=sha256_file(path),
            source_size_bytes=stat.st_size,
            modified_at_utc=modified_at,
            duplicate_count=quality.duplicate_count,
            source_order_violation_count=quality.source_order_violation_count,
            ohlc_violation_count=quality.ohlc_violation_count,
            nonpositive_volume_count=quality.nonpositive_volume_count,
            missing_export_segment_gap_count=quality.missing_export_segment_gap_count,
            unknown_gap_count=quality.unknown_gap_count,
        )
    except (OSError, ValueError) as exc:
        return CandidateRecord(
            path=str(path),
            timeframe=timeframe,
            source_kind=classify_source(path),
            parse_status="FAIL",
            parse_error=str(exc),
            quality_status=None,
            row_count=None,
            first_bar_time=None,
            last_bar_time=None,
            coverage_seconds=None,
            source_sha256=None,
            source_size_bytes=stat.st_size,
            modified_at_utc=modified_at,
            duplicate_count=None,
            source_order_violation_count=None,
            ohlc_violation_count=None,
            nonpositive_volume_count=None,
            missing_export_segment_gap_count=None,
            unknown_gap_count=None,
        )


def _duplicate_groups(records: Iterable[CandidateRecord]) -> tuple[tuple[str, ...], ...]:
    by_hash: dict[str, list[str]] = {}
    for record in records:
        if record.source_sha256:
            by_hash.setdefault(record.source_sha256, []).append(record.path)
    groups = [tuple(sorted(paths)) for paths in by_hash.values() if len(paths) > 1]
    return tuple(sorted(groups))


def summarize_timeframe(
    timeframe: str,
    records: Iterable[CandidateRecord],
) -> TimeframeSummary:
    materialized = tuple(records)
    parseable = tuple(record for record in materialized if record.parse_status == "PASS")
    passing = tuple(record for record in parseable if record.quality_status == "PASS")

    if not passing:
        return TimeframeSummary(
            timeframe=timeframe,
            candidates_total=len(materialized),
            parseable_candidates=len(parseable),
            passing_candidates=0,
            freshest_candidate=None,
            longest_coverage_candidate=None,
            selected_candidate=None,
            recommended_action="NO_PASSING_CANDIDATE",
            duplicate_sha_groups=_duplicate_groups(materialized),
        )

    freshest = max(
        passing,
        key=lambda record: (
            _parse_canonical_time(record.last_bar_time),
            SOURCE_PRIORITY[record.source_kind],
            record.row_count or 0,
        ),
    )
    longest = max(
        passing,
        key=lambda record: (
            record.coverage_seconds or 0,
            record.row_count or 0,
            _parse_canonical_time(record.last_bar_time),
            SOURCE_PRIORITY[record.source_kind],
        ),
    )

    if freshest.path == longest.path:
        selected = freshest.path
        action = "USE_SINGLE_CANDIDATE"
    elif _parse_canonical_time(longest.last_bar_time) >= _parse_canonical_time(
        freshest.last_bar_time
    ):
        selected = longest.path
        action = "USE_LONGEST_COVERAGE_CANDIDATE"
    else:
        selected = None
        action = "RECONCILE_SPLIT_COVERAGE"

    return TimeframeSummary(
        timeframe=timeframe,
        candidates_total=len(materialized),
        parseable_candidates=len(parseable),
        passing_candidates=len(passing),
        freshest_candidate=freshest.path,
        longest_coverage_candidate=longest.path,
        selected_candidate=selected,
        recommended_action=action,
        duplicate_sha_groups=_duplicate_groups(materialized),
    )


def build_inventory(
    roots: Iterable[Path],
    *,
    symbol: str,
    timeframes: Iterable[str],
) -> dict[str, object]:
    normalized_timeframes = tuple(dict.fromkeys(value.upper() for value in timeframes))
    path_records = discover_paths(roots, symbol=symbol, timeframes=normalized_timeframes)
    candidates = tuple(
        inspect_candidate(path, symbol=symbol, timeframe=timeframe)
        for path, timeframe in path_records
    )
    summaries = tuple(
        summarize_timeframe(
            timeframe,
            (record for record in candidates if record.timeframe == timeframe),
        )
        for timeframe in normalized_timeframes
    )
    actions = {summary.recommended_action for summary in summaries}
    if "NO_PASSING_CANDIDATE" in actions:
        status = "FAIL"
    elif "RECONCILE_SPLIT_COVERAGE" in actions:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"

    return {
        "status": status,
        "symbol": symbol.upper(),
        "roots": [str(path) for path in roots],
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summaries": [asdict(summary) for summary in summaries],
        "candidates": [asdict(record) for record in candidates],
    }


def render_inventory(report: dict[str, object]) -> str:
    lines = [
        f"Stage10D Phase 2 dataset inventory: {report['status']}",
        f"Symbol: {report['symbol']}",
    ]
    for summary in report["summaries"]:
        lines.extend(
            (
                "",
                (
                    f"{summary['timeframe']}: candidates={summary['candidates_total']} "
                    f"parseable={summary['parseable_candidates']} "
                    f"passing={summary['passing_candidates']}"
                ),
                f"  action   : {summary['recommended_action']}",
                f"  selected : {summary['selected_candidate'] or '-'}",
                f"  freshest : {summary['freshest_candidate'] or '-'}",
                f"  longest  : {summary['longest_coverage_candidate'] or '-'}",
                f"  duplicate hash groups: {len(summary['duplicate_sha_groups'])}",
            )
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--timeframes", nargs="+", default=("H4", "D1", "M15"))
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_inventory(
        args.roots,
        symbol=args.symbol,
        timeframes=args.timeframes,
    )
    print(render_inventory(report))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"JSON: {args.json_out}")
    return 2 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
