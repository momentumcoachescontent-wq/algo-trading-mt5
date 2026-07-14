"""Build one Stage10D Phase 2 governed canonical dataset manifest."""

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

from python.research.stage10d_data_readiness import TIMEFRAME_SECONDS  # noqa: E402
from python.research.stage10d_governed_manifest import (  # noqa: E402
    build_governed_manifest_bundle,
    write_governed_manifest_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--feed-profile", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=tuple(TIMEFRAME_SECONDS),
    )
    parser.add_argument("--exported-at-utc", default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/stage10d_phase2/canonical_manifests"),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = build_governed_manifest_bundle(
            args.csv_path,
            policy_path=args.policy,
            feed_profile_path=args.feed_profile,
            symbol=args.symbol,
            timeframe=args.timeframe,
            export_timestamp_utc=args.exported_at_utc,
        )
        outputs = write_governed_manifest_bundle(bundle, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    payload = {
        "status": bundle.manifest.governance_status,
        "research_eligible": bundle.manifest.research_eligible,
        "governed_manifest_id": bundle.manifest.governed_manifest_id,
        "raw_data_manifest_id": bundle.manifest.raw_data_manifest_id,
        "symbol": bundle.manifest.symbol,
        "timeframe": bundle.manifest.timeframe,
        "coverage_classification": bundle.manifest.coverage_classification,
        "row_count": bundle.manifest.row_count,
        "first_bar_time": bundle.manifest.first_bar_time,
        "last_bar_time": bundle.manifest.last_bar_time,
        "raw_quality_status": bundle.manifest.raw_quality_status,
        "confirmed_session_gap_count": bundle.manifest.confirmed_session_gap_count,
        "governed_data_gap_count": bundle.manifest.governed_data_gap_count,
        "excluded_bar_times": list(bundle.manifest.excluded_bar_times),
        "outputs": {name: str(path) for name, path in outputs.items()},
        "manifest": asdict(bundle.manifest),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if bundle.manifest.research_eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
