"""Audit Stage10C MT5 logs for D1/H4 context synchronization defects.

The CLI accepts UTF-16 or UTF-8 MT5 log files, reconstructs D1 context
transitions and flags H4/candidate decisions that used a bias inconsistent with
the latest D1 snapshot.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from python.research.d1_context_contract import (
    D1ContextSnapshot,
    candidate_direction_bias,
    check_bias_synchronization,
    specific_block_reason,
)

_D1_DEBUG_RE = re.compile(
    r"\[D1_DEBUG\]\s+(?P<symbol>\w+)\s+\|\s+D1=(?P<d1_bar>\d{4}\.\d{2}\.\d{2})"
    r"\s+\|\s+structure=(?P<structure>-?\d+)"
    r"\s+\|\s+has_structure=(?P<has_structure>true|false)"
    r".*?emaRising=(?P<ema_rising>true|false)"
    r"\s+\|\s+emaFalling=(?P<ema_falling>true|false)"
    r".*?d1Above=(?P<d1_above>true|false)"
    r"\s+\|\s+d1Below=(?P<d1_below>true|false)"
    r"\s+\|\s+h4Above=(?P<h4_above>true|false)"
    r"\s+\|\s+h4Below=(?P<h4_below>true|false)"
    r".*?bias=(?P<logged_bias>-?\d+)"
)

_H4_DEBUG_RE = re.compile(
    r"\[H4_SIGNAL_DEBUG\]\s+(?P<bar>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})"
    r"\s+\|\s+(?P<symbol>\w+)\s+\|\s+bias=(?P<bias>[+-]?\d+)"
)

_ML_CANDIDATE_RE = re.compile(
    r"\[ML_VETO_SHADOW\].*?eval_time=(?P<eval_time>[^|]+?)\s+\|"
    r".*?evaluated=(?P<evaluated>true|false)\s+\|\s+direction=(?P<direction>\w+)"
)

_DECISION_RE = re.compile(
    r"\[DECISION_BLOCKED\].*?eval_time=(?P<eval_time>[^|]+?)\s+\|"
    r".*?reason=(?P<reason>[^|]+?)\s+\|"
)

_D1_WEIGHTED_RE = re.compile(
    r"\[D1_BIAS_C1\].*?eval_time=(?P<eval_time>[^|]+?)\s+\|"
    r".*?bias_d1=(?P<weighted>-?\d+(?:\.\d+)?)"
)

_RESTART_RE = re.compile(r"\[(?:EA_DEINIT|SCOPE_INIT)\]")


def _as_bool(value: str) -> bool:
    return value == "true"


def read_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class AuditFinding:
    finding_type: str
    source_file: str
    line_number: int
    event_time: str
    snapshot_id: str
    expected_bias: int
    observed_bias: int
    context_reason: str
    detail: str


@dataclass(frozen=True)
class AuditSummary:
    files: int
    d1_snapshots: int
    d1_transitions: int
    stale_h4_bias_events: int
    stale_candidate_events: int
    generic_no_bias_events: int
    findings: tuple[AuditFinding, ...]

    @property
    def stale_events(self) -> int:
        return self.stale_h4_bias_events + self.stale_candidate_events

    def to_dict(self) -> dict:
        result = asdict(self)
        result["stale_events"] = self.stale_events
        return result


def iter_lines(paths: Iterable[Path]) -> Iterator[tuple[Path, int, str]]:
    for path in sorted(paths, key=lambda item: item.name):
        for line_number, line in enumerate(read_log(path).splitlines(), start=1):
            yield path, line_number, line


def audit_paths(paths: Iterable[Path]) -> AuditSummary:
    selected = tuple(sorted(paths, key=lambda item: item.name))
    current: Optional[D1ContextSnapshot] = None
    previous_snapshot_id: Optional[str] = None
    latest_weighted_bias: Optional[float] = None
    findings: list[AuditFinding] = []
    snapshots = 0
    transitions = 0
    stale_h4 = 0
    stale_candidates = 0
    generic_no_bias = 0

    for path, line_number, line in iter_lines(selected):
        weighted_match = _D1_WEIGHTED_RE.search(line)
        if weighted_match:
            latest_weighted_bias = float(weighted_match.group("weighted"))

        d1_match = _D1_DEBUG_RE.search(line)
        if d1_match:
            groups = d1_match.groupdict()
            snapshot = D1ContextSnapshot(
                symbol=groups["symbol"],
                d1_bar=groups["d1_bar"],
                structure=int(groups["structure"]),
                has_structure=_as_bool(groups["has_structure"]),
                ema_rising=_as_bool(groups["ema_rising"]),
                ema_falling=_as_bool(groups["ema_falling"]),
                d1_above_ema=_as_bool(groups["d1_above"]),
                d1_below_ema=_as_bool(groups["d1_below"]),
                h4_above_ema=_as_bool(groups["h4_above"]),
                h4_below_ema=_as_bool(groups["h4_below"]),
                weighted_bias=latest_weighted_bias,
            )
            logged_bias = int(groups["logged_bias"])
            if logged_bias != snapshot.discrete_bias:
                findings.append(
                    AuditFinding(
                        finding_type="d1_contract_mismatch",
                        source_file=path.name,
                        line_number=line_number,
                        event_time=snapshot.d1_bar,
                        snapshot_id=snapshot.snapshot_id,
                        expected_bias=snapshot.discrete_bias,
                        observed_bias=logged_bias,
                        context_reason=snapshot.reason.value,
                        detail="Logged D1 bias does not match the reference contract.",
                    )
                )
            snapshots += 1
            if snapshot.snapshot_id != previous_snapshot_id:
                transitions += 1
            current = snapshot
            previous_snapshot_id = snapshot.snapshot_id
            continue

        if current is None:
            continue

        h4_match = _H4_DEBUG_RE.search(line)
        if h4_match:
            observed = int(h4_match.group("bias"))
            check = check_bias_synchronization(current, observed)
            if check.stale:
                stale_h4 += 1
                findings.append(
                    AuditFinding(
                        finding_type="stale_h4_bias",
                        source_file=path.name,
                        line_number=line_number,
                        event_time=h4_match.group("bar").strip(),
                        snapshot_id=current.snapshot_id,
                        expected_bias=check.expected_bias,
                        observed_bias=check.observed_bias,
                        context_reason=current.reason.value,
                        detail="H4 signal debug used a bias different from the latest D1 snapshot.",
                    )
                )
            continue

        candidate_match = _ML_CANDIDATE_RE.search(line)
        if candidate_match and candidate_match.group("evaluated") == "true":
            direction = candidate_match.group("direction")
            observed = candidate_direction_bias(direction)
            if current.discrete_bias == 0 and observed != 0:
                stale_candidates += 1
                findings.append(
                    AuditFinding(
                        finding_type="candidate_while_d1_neutral",
                        source_file=path.name,
                        line_number=line_number,
                        event_time=candidate_match.group("eval_time").strip(),
                        snapshot_id=current.snapshot_id,
                        expected_bias=0,
                        observed_bias=observed,
                        context_reason=current.reason.value,
                        detail=(
                            f"Candidate direction={direction} was generated while "
                            "the latest D1 snapshot resolved to neutral."
                        ),
                    )
                )
            continue

        decision_match = _DECISION_RE.search(line)
        if decision_match:
            reason = decision_match.group("reason").strip()
            if reason == "no_bias_context":
                generic_no_bias += 1
                findings.append(
                    AuditFinding(
                        finding_type="generic_no_bias_reason",
                        source_file=path.name,
                        line_number=line_number,
                        event_time=decision_match.group("eval_time").strip(),
                        snapshot_id=current.snapshot_id,
                        expected_bias=current.discrete_bias,
                        observed_bias=0,
                        context_reason=current.reason.value,
                        detail=(
                            "Replace generic no_bias_context telemetry with "
                            f"{specific_block_reason(current)}."
                        ),
                    )
                )
            continue

        _RESTART_RE.search(line)

    return AuditSummary(
        files=len(selected),
        d1_snapshots=snapshots,
        d1_transitions=transitions,
        stale_h4_bias_events=stale_h4,
        stale_candidate_events=stale_candidates,
        generic_no_bias_events=generic_no_bias,
        findings=tuple(findings),
    )


def discover_paths(inputs: Iterable[str]) -> tuple[Path, ...]:
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            log_paths = sorted(path.glob("*.log"))
            paths.extend(log_paths or sorted(path.glob("*.txt")))
        elif path.is_file():
            paths.append(path)
        else:
            raise FileNotFoundError(raw)
    unique = {path.resolve(): path for path in paths}
    return tuple(sorted(unique.values(), key=lambda item: item.name))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="MT5 log files or directories")
    parser.add_argument("--json-out", type=Path, help="Optional output JSON path")
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit with status 2 when stale D1/H4 state is detected",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    summary = audit_paths(discover_paths(args.inputs))
    payload = summary.to_dict()
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    if args.fail_on_stale and summary.stale_events:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
