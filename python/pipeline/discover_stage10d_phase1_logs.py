"""Discover the complete local MT5 log set for the Stage10D Phase 1 gate.

MetaTrader can split one EA session across daily files and writes separate log
streams under ``MQL5/Logs`` and ``Logs``. The final gate needs the latest
v4.43.1 ``on_init`` plus the latest organic ``D1_CONTEXT_SNAPSHOT`` from the
same source directory. Selecting only the most recently modified file can pick
an evaluation-only fragment and lose the session start.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from python.pipeline.validate_stage10d_phase1_shadow import EA_MARKER, read_log

SESSION_START = "[ENTRY_STATE_RESET]"
EVALUATION_MARKER = "[D1_CONTEXT_SNAPSHOT]"


@dataclass(frozen=True)
class LogInfo:
    path: Path
    sort_key: tuple[str, int]
    has_init: bool
    has_evaluation: bool


def inspect_log(path: Path) -> Optional[LogInfo]:
    try:
        text = read_log(path)
    except OSError:
        return None

    if EA_MARKER not in text:
        return None

    v4431_lines = [line for line in text.splitlines() if EA_MARKER in line]
    has_init = any(
        SESSION_START in line and "reason=on_init" in line for line in v4431_lines
    )
    has_evaluation = any(EVALUATION_MARKER in line for line in v4431_lines)
    return LogInfo(
        path=path,
        sort_key=(path.name, path.stat().st_mtime_ns),
        has_init=has_init,
        has_evaluation=has_evaluation,
    )


def inspect_directory(directory: Path) -> list[LogInfo]:
    if not directory.is_dir():
        return []
    infos = [inspect_log(path) for path in directory.glob("*.log")]
    return sorted((info for info in infos if info is not None), key=lambda item: item.sort_key)


def select_from_directory(infos: Iterable[LogInfo]) -> tuple[LogInfo, ...]:
    ordered = tuple(sorted(infos, key=lambda item: item.sort_key))
    init_logs = [info for info in ordered if info.has_init]
    if not init_logs:
        return ()

    evaluation_logs = [info for info in ordered if info.has_evaluation]
    if not evaluation_logs:
        return (init_logs[-1],)

    latest_evaluation = evaluation_logs[-1]
    eligible_inits = [info for info in init_logs if info.sort_key <= latest_evaluation.sort_key]
    if not eligible_inits:
        return ()
    latest_init = eligible_inits[-1]

    selected = tuple(
        info
        for info in ordered
        if latest_init.sort_key <= info.sort_key <= latest_evaluation.sort_key
    )
    return selected or (latest_init, latest_evaluation)


def discover_logs(mt5_root: Path) -> tuple[Path, ...]:
    search_dirs = (
        mt5_root / "MQL5" / "Logs",
        mt5_root / "Logs",
    )

    candidates: list[tuple[int, tuple[str, int], tuple[LogInfo, ...]]] = []
    for directory in search_dirs:
        selected = select_from_directory(inspect_directory(directory))
        if not selected:
            continue
        has_evaluation = int(any(info.has_evaluation for info in selected))
        latest_key = max(info.sort_key for info in selected)
        candidates.append((has_evaluation, latest_key, selected))

    if not candidates:
        searched = ", ".join(str(path) for path in search_dirs)
        raise FileNotFoundError(
            "No complete Stage10D v4.43.1 session found. Searched: " + searched
        )

    _, _, best = max(candidates, key=lambda item: (item[0], item[1]))
    return tuple(info.path for info in best)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mt5_root", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = discover_logs(args.mt5_root)
    except FileNotFoundError as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 1

    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
