"""Render concise failure details from a Stage10D Phase 2 inventory JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional


def render_diagnostics(report: dict[str, object]) -> str:
    lines = [
        f"Stage10D Phase 2 inventory diagnostics: {report.get('status', 'UNKNOWN')}",
        f"Symbol: {report.get('symbol', '-')}",
    ]
    candidates = report.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("Inventory JSON field 'candidates' must be a list")

    for record in candidates:
        if not isinstance(record, dict):
            continue
        timeframe = record.get("timeframe", "-")
        path = record.get("path", "-")
        lines.extend(("", f"{timeframe}: {path}"))
        parse_status = record.get("parse_status")
        if parse_status != "PASS":
            lines.append(f"  parse_status : {parse_status}")
            lines.append(f"  parse_error  : {record.get('parse_error') or '-'}")
            continue

        lines.extend(
            (
                f"  quality      : {record.get('quality_status')}",
                (
                    f"  coverage     : rows={record.get('row_count')} "
                    f"from={record.get('first_bar_time')} to={record.get('last_bar_time')}"
                ),
                (
                    "  violations   : "
                    f"duplicates={record.get('duplicate_count')} "
                    f"order={record.get('source_order_violation_count')} "
                    f"ohlc={record.get('ohlc_violation_count')} "
                    f"volume={record.get('nonpositive_volume_count')}"
                ),
                (
                    "  gaps         : "
                    f"missing_export_segment={record.get('missing_export_segment_gap_count')} "
                    f"unknown={record.get('unknown_gap_count')}"
                ),
                f"  sha256       : {record.get('source_sha256') or '-'}",
            )
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_json", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = json.loads(args.inventory_json.read_text(encoding="utf-8"))
        print(render_diagnostics(report))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Inventory diagnostics error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
