"""Discover the complete local MT5 log set for the Stage10D Phase 1 gate.

MetaTrader can split one EA session across daily files and writes separate log
streams under ``MQL5/Logs`` and ``Logs``. Discovery is anchored on the latest
v4.43.1 ``on_init`` event. Only snapshots at or after that init belong to the
current session; an older completed session must never satisfy the final gate
after the EA has restarted.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.pipeline.validate_stage10d_phase1_shadow import EA_MARKER, read_log

SESSION_START = "[ENTRY_STATE_RESET]"
EVALUATION_MARKER = "[D1_CONTEXT_SNAPSHOT]"
EventKey = tuple[str, int, int]


@dataclass(frozen=True)
class LogInfo:
    path: Path
    sort_key: tuple[str, int]
    init_lines: tuple[int, ...]
    evaluation_lines: tuple[int, ...]

    def event_key(self, line_index: int) -> EventKey:
        return (self.sort_key[0], self.sort_key[1], line_index)

    @property
    def has_init(self) -> bool:
        return bool(self.init_lines)

    @property
    def has_evaluation(self) -> bool:
        return bool(self.evaluation_lines)


def inspect_log(path: Path) -> Optional[LogInfo]:
    try:
        text = read_log(path)
    except OSError:
        return None

    lines = text.splitlines()
    if not any(EA_MARKER in line for line in lines):
        return None

    init_lines = tuple(
        index
        for index, line in enumerate(lines)
        if EA_MARKER in line
        and SESSION_START in line
        and "reason=on_init" in line
    )
    evaluation_lines = tuple(
        index
        for index, line in enumerate(lines)
        if EA_MARKER in line and EVALUATION_MARKER in line
    )
    return LogInfo(
        path=path,
        sort_key=(path.name, path.stat().st_mtime_ns),
        init_lines=init_lines,
        evaluation_lines=evaluation_lines,
    )


def inspect_directory(directory: Path) -> list[LogInfo]:
    if not directory.is_dir():
        return []
    infos = [inspect_log(path) for path in directory.glob("*.log")]
    return sorted((info for info in infos if info is not None), key=lambda item: item.sort_key)


def latest_init_event(infos: Iterable[LogInfo]) -> Optional[tuple[EventKey, LogInfo]]:
    events = [
        (info.event_key(line_index), info)
        for info in infos
        for line_index in info.init_lines
    ]
    return max(events, key=lambda item: item[0]) if events else None


def select_from_directory(infos: Iterable[LogInfo]) -> tuple[LogInfo, ...]:
    ordered = tuple(sorted(infos, key=lambda item: item.sort_key))
    latest_init = latest_init_event(ordered)
    if latest_init is None:
        return ()

    latest_init_key, latest_init_info = latest_init
    post_init_evaluations = [
        (info.event_key(line_index), info)
        for info in ordered
        for line_index in info.evaluation_lines
        if info.event_key(line_index) >= latest_init_key
    ]

    if post_init_evaluations:
        _, end_info = max(post_init_evaluations, key=lambda item: item[0])
    else:
        end_info = ordered[-1]

    selected = tuple(
        info
        for info in ordered
        if latest_init_info.sort_key <= info.sort_key <= end_info.sort_key
    )
    return selected or (latest_init_info,)


def discover_logs(mt5_root: Path) -> tuple[Path, ...]:
    search_dirs = (
        mt5_root / "MQL5" / "Logs",
        mt5_root / "Logs",
    )

    candidates: list[tuple[EventKey, tuple[LogInfo, ...]]] = []
    for directory in search_dirs:
        inspected = inspect_directory(directory)
        latest_init = latest_init_event(inspected)
        if latest_init is None:
            continue
        selected = select_from_directory(inspected)
        if not selected:
            continue
        latest_init_key, _ = latest_init
        candidates.append((latest_init_key, selected))

    if not candidates:
        searched = ", ".join(str(path) for path in search_dirs)
        raise FileNotFoundError(
            "No complete Stage10D v4.43.1 session found. Searched: " + searched
        )

    _, best = max(candidates, key=lambda item: item[0])
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
        print(str(exc), file=sys.stderr)
        return 1

    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
