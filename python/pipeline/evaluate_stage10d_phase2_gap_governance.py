"""Evaluate Stage10D Phase 2 gap governance for one MT5 CSV dataset."""

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

from python.research.stage10d_data_readiness import load_mt5_csv  # noqa: E402
from python.research.stage10d_gap_governance import (  # noqa: E402
    evaluate_gap_governance,
    load_gap_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True, choices=("H4", "D1", "M15"))
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = load_mt5_csv(args.csv_path, symbol=args.symbol, timeframe=args.timeframe)
        policy = load_gap_policy(args.policy)
        report = evaluate_gap_governance(
            rows,
            symbol=args.symbol,
            timeframe=args.timeframe,
            policy=policy,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    payload = asdict(report)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return 0 if report.status in {"PASS", "PASS_WITH_GOVERNED_EXCLUSIONS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
