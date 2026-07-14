"""Inspect only non-market-closure gaps in canonical Stage10D Phase 2 exports.

This command is read-only. It loads the selected MT5 CSV files with the canonical
Phase 2 parser and prints only gaps that are not already classified as expected
weekend market closures. It is intended to distinguish genuine missing export
segments from routine weekly closures before any broker-session exception is
approved.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.research.stage10d_data_readiness import audit_rows, load_mt5_csv  # noqa: E402


def inspect_problem_gaps(
    exports_root: Path,
    *,
    symbol: str,
    timeframes: tuple[str, ...],
) -> dict[str, object]:
    datasets: list[dict[str, object]] = []
    parse_failures = 0
    problem_gap_count = 0

    for timeframe in timeframes:
        normalized_timeframe = timeframe.upper()
        path = exports_root / f"{symbol.upper()}_{normalized_timeframe}.csv"
        try:
            rows = load_mt5_csv(path, symbol=symbol, timeframe=normalized_timeframe)
            quality = audit_rows(rows, timeframe=normalized_timeframe)
            problem_gaps = tuple(
                gap
                for gap in quality.gaps
                if gap.classification != "expected_market_closure"
            )
            problem_gap_count += len(problem_gaps)
            datasets.append(
                {
                    "timeframe": normalized_timeframe,
                    "path": str(path),
                    "parse_status": "PASS",
                    "parse_error": None,
                    "quality_status": quality.status,
                    "row_count": quality.row_count,
                    "duplicate_count": quality.duplicate_count,
                    "source_order_violation_count": quality.source_order_violation_count,
                    "ohlc_violation_count": quality.ohlc_violation_count,
                    "nonpositive_volume_count": quality.nonpositive_volume_count,
                    "expected_market_closure_gap_count": quality.expected_market_closure_gap_count,
                    "problem_gap_count": len(problem_gaps),
                    "problem_gaps": [asdict(gap) for gap in problem_gaps],
                }
            )
        except (OSError, ValueError) as exc:
            parse_failures += 1
            datasets.append(
                {
                    "timeframe": normalized_timeframe,
                    "path": str(path),
                    "parse_status": "FAIL",
                    "parse_error": str(exc),
                    "quality_status": None,
                    "row_count": None,
                    "duplicate_count": None,
                    "source_order_violation_count": None,
                    "ohlc_violation_count": None,
                    "nonpositive_volume_count": None,
                    "expected_market_closure_gap_count": None,
                    "problem_gap_count": None,
                    "problem_gaps": [],
                }
            )

    if parse_failures:
        status = "ERROR"
    elif problem_gap_count:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"

    return {
        "status": status,
        "symbol": symbol.upper(),
        "exports_root": str(exports_root),
        "problem_gap_count": problem_gap_count,
        "parse_failures": parse_failures,
        "datasets": datasets,
    }


def render_report(report: dict[str, object]) -> str:
    lines = [
        f"Stage10D Phase 2 problem-gap inspection: {report['status']}",
        f"Symbol: {report['symbol']}",
        f"Root: {report['exports_root']}",
    ]

    for dataset in report["datasets"]:
        lines.extend(("", f"=== {dataset['timeframe']} ==="))
        if dataset["parse_status"] != "PASS":
            lines.append(f"parse_error={dataset['parse_error']}")
            continue

        lines.append(
            " ".join(
                (
                    f"quality={dataset['quality_status']}",
                    f"rows={dataset['row_count']}",
                    f"duplicates={dataset['duplicate_count']}",
                    f"order={dataset['source_order_violation_count']}",
                    f"ohlc={dataset['ohlc_violation_count']}",
                    f"volume={dataset['nonpositive_volume_count']}",
                    f"expected_closure={dataset['expected_market_closure_gap_count']}",
                    f"problem_gaps={dataset['problem_gap_count']}",
                )
            )
        )
        for gap in dataset["problem_gaps"]:
            lines.append(
                f"{gap['previous_time']} -> {gap['current_time']} | "
                f"missing={gap['missing_bars']} | "
                f"delta_seconds={gap['delta_seconds']} | "
                f"class={gap['classification']}"
            )

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports_root", type=Path)
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--timeframes", nargs="+", default=("H4", "D1", "M15"))
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = inspect_problem_gaps(
        args.exports_root,
        symbol=args.symbol,
        timeframes=tuple(args.timeframes),
    )
    print(render_report(report))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"JSON: {args.json_out}")
    if report["status"] == "ERROR":
        return 1
    if report["status"] == "REVIEW_REQUIRED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
