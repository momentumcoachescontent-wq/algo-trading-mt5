#!/usr/bin/env python3
"""CLI for the Demo Acceleration Stage 1 governance contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.governance.demo_acceleration_contract import load_contract, validate_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that the Demo Acceleration program preserves the Stage10C "
            "control, challenger-specific gates, isolation, and no-activation boundary."
        )
    )
    parser.add_argument(
        "contract",
        type=Path,
        help="Path to the Demo Acceleration JSON contract.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = load_contract(args.contract)
        result = validate_contract(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_GOVERNANCE_CONTRACT",
                    "contract": str(args.contract),
                    "errors": [str(exc)],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    output = {
        **result.to_dict(),
        "contract": str(args.contract),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
