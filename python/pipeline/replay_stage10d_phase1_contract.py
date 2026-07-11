"""Deterministic contract replay for the July 8, 2026 D1/H4 defect.

This is not a price backtest. It replays the recorded context/candidate facts
that exposed the v4.43.0 orchestration defect and verifies the v4.43.1 gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.research.h4_d1_gate_contract import gate_h4_signal


@dataclass(frozen=True)
class ReplayEvent:
    eval_time: str
    structure: int
    bullish_components: bool
    discrete_bias: int
    weighted_bias: float
    raw_h4_signal: int


EVENTS = (
    ReplayEvent(
        eval_time="2026-07-08 00:00",
        structure=-1,
        bullish_components=True,
        discrete_bias=0,
        weighted_bias=0.400,
        raw_h4_signal=1,
    ),
    ReplayEvent(
        eval_time="2026-07-08 04:00",
        structure=-1,
        bullish_components=True,
        discrete_bias=0,
        weighted_bias=0.400,
        raw_h4_signal=1,
    ),
)


def run_replay() -> dict:
    rows = []
    defects_prevented = 0

    for event in EVENTS:
        decision = gate_h4_signal(
            raw_signal=event.raw_h4_signal,
            discrete_bias=event.discrete_bias,
            snapshot_match=True,
        )
        passed = (
            decision.filtered_signal == 0
            and decision.reason == "d1_neutral_blocks_h4_signal"
        )
        defects_prevented += int(passed and event.raw_h4_signal != 0)
        rows.append(
            {
                **asdict(event),
                "v4430_observed_candidate": event.raw_h4_signal,
                "v4431_filtered_signal": decision.filtered_signal,
                "v4431_reason": decision.reason,
                "pass": passed,
            }
        )

    return {
        "replay_type": "recorded_contract_replay_not_price_backtest",
        "case": "USDJPY July 8 2026 neutral D1 conflict with raw BUY candidate",
        "events": rows,
        "events_total": len(rows),
        "events_passed": sum(int(row["pass"]) for row in rows),
        "defective_promotions_prevented": defects_prevented,
        "pass": all(row["pass"] for row in rows),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_replay()
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
