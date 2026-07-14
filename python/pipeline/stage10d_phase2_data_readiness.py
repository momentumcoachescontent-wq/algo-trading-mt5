"""Build a Stage10D Phase 2 manifest and quality report from an MT5 CSV export."""

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

from python.research.stage10d_data_readiness import (  # noqa: E402
    TIMEFRAME_SECONDS,
    build_readiness_bundle,
    write_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Canonical same-broker MT5 CSV export")
    parser.add_argument("--symbol", required=True, help="Example: USDJPY")
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=tuple(TIMEFRAME_SECONDS),
        help="Dataset timeframe",
    )
    parser.add_argument("--broker", required=True, help="Broker/feed identity")
    parser.add_argument("--terminal", required=True, help="Terminal/environment identity")
    parser.add_argument(
        "--server-timezone",
        required=True,
        help="Explicit broker-server timezone/offset convention; timestamps are not converted",
    )
    parser.add_argument(
        "--exported-at-utc",
        default=None,
        help="Optional export timestamp in ISO-8601 UTC form",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/stage10d_phase2"),
    )
    parser.add_argument(
        "--allow-quality-fail",
        action="store_true",
        help="Write artifacts but return zero even when the data-quality gate fails",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = build_readiness_bundle(
            args.csv_path,
            symbol=args.symbol,
            timeframe=args.timeframe,
            broker=args.broker,
            terminal=args.terminal,
            server_timezone=args.server_timezone,
            export_timestamp_utc=args.exported_at_utc,
        )
        outputs = write_bundle(bundle, args.output_dir)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    result = {
        "status": bundle.quality.status,
        "data_manifest_id": bundle.manifest.data_manifest_id,
        "symbol": bundle.manifest.symbol,
        "timeframe": bundle.manifest.timeframe,
        "row_count": bundle.manifest.row_count,
        "first_bar_time": bundle.manifest.first_bar_time,
        "last_bar_time": bundle.manifest.last_bar_time,
        "source_sha256": bundle.manifest.source_sha256,
        "quality": asdict(bundle.quality),
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if bundle.quality.status == "FAIL" and not args.allow_quality_fail:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
