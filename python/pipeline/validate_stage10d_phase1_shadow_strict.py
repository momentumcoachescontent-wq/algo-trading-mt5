"""Strict Stage10D Phase 1 shadow validator for mixed MT5 logs.

MT5 writes multiple EAs into the same daily log. This wrapper filters the input
to the v4.43.1 EA marker before delegating to the canonical Phase 1 validator,
preventing v4.43.0 real-EA order or webhook events from contaminating the
shadow gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional

from python.pipeline.validate_stage10d_phase1_shadow import (
    EA_MARKER,
    ValidationSummary,
    read_log,
    validate_lines,
)


def strict_lines(paths: Iterable[Path]) -> list[str]:
    """Return only log lines emitted by the v4.43.1 shadow EA."""

    lines: list[str] = []
    for path in paths:
        lines.extend(
            line
            for line in read_log(path).splitlines()
            if EA_MARKER in line
        )
    return lines


def validate_paths_strict(
    paths: Iterable[Path],
    expected_magic: int = 20260711,
) -> ValidationSummary:
    return validate_lines(strict_lines(paths), expected_magic=expected_magic)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--expected-magic", type=int, default=20260711)
    parser.add_argument("--require-evaluation", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    summary = validate_paths_strict(args.logs, expected_magic=args.expected_magic)
    rendered = json.dumps(summary.to_dict(), indent=2, ensure_ascii=False)
    print(rendered)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")

    if summary.status == "FAIL":
        return 2
    if args.require_evaluation and summary.evaluations == 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
