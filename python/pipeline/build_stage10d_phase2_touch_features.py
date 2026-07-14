"""Build governed Stage10D H4 directional touch-gap features."""

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

from python.research.stage10d_touch_features import (  # noqa: E402
    DEFAULT_ATR_PERIOD,
    DEFAULT_EMA_PERIOD,
    DEFAULT_EXACT_ATR,
    DEFAULT_EXTENDED_ATR,
    DEFAULT_SOFT_ATR,
    TouchThresholds,
    build_touch_artifact,
    write_touch_artifact,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--governed-manifest", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/stage10d_phase2/touch_features"),
    )
    parser.add_argument("--ema-period", type=int, default=DEFAULT_EMA_PERIOD)
    parser.add_argument("--atr-period", type=int, default=DEFAULT_ATR_PERIOD)
    parser.add_argument("--exact-atr", type=float, default=DEFAULT_EXACT_ATR)
    parser.add_argument("--soft-atr", type=float, default=DEFAULT_SOFT_ATR)
    parser.add_argument("--extended-atr", type=float, default=DEFAULT_EXTENDED_ATR)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = TouchThresholds(
        exact_atr=args.exact_atr,
        soft_atr=args.soft_atr,
        extended_atr=args.extended_atr,
    )
    try:
        artifact, features = build_touch_artifact(
            args.csv_path,
            args.governed_manifest,
            thresholds=thresholds,
            ema_period=args.ema_period,
            atr_period=args.atr_period,
        )
        outputs = write_touch_artifact(artifact, features, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    buy_defined = sum(row["touch_gap_buy_atr"] is not None for row in features)
    sell_defined = sum(row["touch_gap_sell_atr"] is not None for row in features)
    result = {
        "status": "PASS",
        "feature_artifact_id": artifact.feature_artifact_id,
        "governed_manifest_id": artifact.governed_manifest_id,
        "symbol": artifact.symbol,
        "timeframe": artifact.timeframe,
        "row_count": artifact.row_count,
        "eligible_row_count": artifact.eligible_row_count,
        "ineligible_row_count": artifact.ineligible_row_count,
        "segment_reset_count": artifact.segment_reset_count,
        "buy_directionally_defined_count": buy_defined,
        "sell_directionally_defined_count": sell_defined,
        "thresholds": {
            "exact_atr": artifact.exact_atr,
            "soft_atr": artifact.soft_atr,
            "extended_atr": artifact.extended_atr,
        },
        "outputs": {name: str(path) for name, path in outputs.items()},
        "manifest": asdict(artifact),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
