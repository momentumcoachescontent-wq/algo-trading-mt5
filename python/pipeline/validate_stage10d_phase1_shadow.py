"""Validate a v4.43.1 Stage10C D1-context-integrity shadow log.

The validator scopes itself to the latest v4.43.1 initialization session and
checks startup safety, webhook authentication, Magic isolation and every
available D1/H4 snapshot contract. It can be run before the first H4 evaluation
(startup-only PASS) or with --require-evaluation for the final Phase 1 gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EA_MARKER = "EMA_MTF_v4431_stage10c_d1_context_integrity"
SESSION_START = "[ENTRY_STATE_RESET]"
ORDER_MARKERS = (
    "[ORDER_SEND]",
    "[ORDER_SENT]",
    "[TRADE_OPEN]",
    "[ENTRY_ACCEPTED]",
    "[TRADE_OPEN_BUY]",
    "[TRADE_OPEN_SELL]",
)


def read_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse_pipe_fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for segment in line.split("|"):
        segment = segment.strip()
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        key = key.strip().split()[-1]
        fields[key] = value.strip()
    return fields


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class EvaluationResult:
    eval_time: str
    bias_discrete: int
    raw_h4_signal: int
    filtered_h4_signal: int
    snapshot_match: bool
    passed: bool
    violations: tuple[str, ...]


@dataclass(frozen=True)
class ValidationSummary:
    status: str
    session_lines: int
    expected_magic: int
    observed_magic: Optional[int]
    evaluations: int
    edge_webhook_ok: int
    checks: tuple[Check, ...]
    evaluation_results: tuple[EvaluationResult, ...]

    @property
    def failed_checks(self) -> int:
        return sum(check.status == "FAIL" for check in self.checks)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["failed_checks"] = self.failed_checks
        return result


def latest_session(lines: list[str]) -> list[str]:
    starts = [
        index
        for index, line in enumerate(lines)
        if EA_MARKER in line
        and SESSION_START in line
        and "reason=on_init" in line
    ]
    if not starts:
        return []
    return lines[starts[-1] :]


def validate_lines(lines: Iterable[str], expected_magic: int = 20260711) -> ValidationSummary:
    all_lines = list(lines)
    session = latest_session(all_lines)
    checks: list[Check] = []
    eval_results: list[EvaluationResult] = []

    if not session:
        checks.append(Check("latest_v4431_session", "FAIL", "No v4.43.1 on_init session found."))
        return ValidationSummary(
            status="FAIL",
            session_lines=0,
            expected_magic=expected_magic,
            observed_magic=None,
            evaluations=0,
            edge_webhook_ok=0,
            checks=tuple(checks),
            evaluation_results=(),
        )

    checks.append(Check("latest_v4431_session", "PASS", "Latest v4.43.1 session isolated."))

    scope_line = next((line for line in session if "[SCOPE_INIT]" in line), "")
    scope_ok = (
        "resolved_mode=SHADOW_ONLY" in scope_line
        and "order_send_allowed=false" in scope_line
    )
    checks.append(
        Check(
            "shadow_execution_scope",
            "PASS" if scope_ok else "FAIL",
            "SHADOW_ONLY and order_send_allowed=false required.",
        )
    )

    magic_line = next((line for line in session if "[MFE_TRACKER_INIT]" in line), "")
    magic_match = re.search(r"magic=(\d+)", magic_line)
    observed_magic = int(magic_match.group(1)) if magic_match else None
    checks.append(
        Check(
            "magic_isolation",
            "PASS" if observed_magic == expected_magic else "FAIL",
            f"expected={expected_magic} observed={observed_magic}",
        )
    )

    init_line = next((line for line in session if "[INIT_V2_LOG]" in line), "")
    init_safe = (
        '"ea_version":"v4.43.1"' in init_line
        and '"execution_mode":"SHADOW_ONLY"' in init_line
        and '"capital_enabled":false' in init_line
        and '"order_send_allowed":false' in init_line
    )
    checks.append(
        Check(
            "init_payload_safety",
            "PASS" if init_safe else "FAIL",
            "v4.43.1 init payload must be capital-disabled shadow.",
        )
    )

    webhook_ok = any(
        "[F5A4_WEBHOOK_OK]" in line
        and "event=ea_init" in line
        and "status=200" in line
        for line in session
    )
    checks.append(
        Check(
            "ea_init_webhook",
            "PASS" if webhook_ok else "FAIL",
            "Authenticated ea_init webhook status=200 required.",
        )
    )

    order_lines = [line for line in session if any(marker in line for marker in ORDER_MARKERS)]
    checks.append(
        Check(
            "no_order_activity",
            "PASS" if not order_lines else "FAIL",
            f"order-like events detected={len(order_lines)}",
        )
    )

    snapshot_lines = [line for line in session if "[D1_CONTEXT_SNAPSHOT]" in line]
    edge_webhook_ok = sum("[EDGE_EVAL_WEBHOOK_OK]" in line for line in session)

    for line in snapshot_lines:
        fields = parse_pipe_fields(line)
        violations: list[str] = []
        try:
            bias = int(fields["bias_discrete"])
            raw = int(fields["raw_h4_signal"])
            filtered = int(fields["filtered_h4_signal"])
            snapshot_match = as_bool(fields["snapshot_match"])
            consumed_bias = int(fields["h4_consumed_bias"])
            snapshot_id = fields["snapshot_id"].strip()
            consumed_snapshot_id = fields["h4_consumed_snapshot_id"].strip()
            missing_identity = [
                name
                for name, value in (
                    ("snapshot_id", snapshot_id),
                    ("h4_consumed_snapshot_id", consumed_snapshot_id),
                )
                if not value
            ]
            if missing_identity:
                raise ValueError("missing_snapshot_identity:" + ",".join(missing_identity))
        except (KeyError, ValueError) as exc:
            eval_results.append(
                EvaluationResult(
                    eval_time=fields.get("eval_time", "unknown"),
                    bias_discrete=0,
                    raw_h4_signal=0,
                    filtered_h4_signal=0,
                    snapshot_match=False,
                    passed=False,
                    violations=(f"malformed_snapshot:{exc}",),
                )
            )
            continue

        if not snapshot_match:
            violations.append("snapshot_match_false")
        if snapshot_id != consumed_snapshot_id:
            violations.append("snapshot_id_mismatch")
        if consumed_bias != bias:
            violations.append("consumed_bias_mismatch")
        if bias == 0 and filtered != 0:
            violations.append("neutral_bias_promoted_signal")
        if raw != 0 and bias != 0 and raw != bias and filtered != 0:
            violations.append("opposite_bias_promoted_signal")
        if filtered != 0 and not (filtered == raw == bias):
            violations.append("filtered_signal_not_raw_bias_aligned")

        eval_results.append(
            EvaluationResult(
                eval_time=fields.get("eval_time", "unknown"),
                bias_discrete=bias,
                raw_h4_signal=raw,
                filtered_h4_signal=filtered,
                snapshot_match=snapshot_match,
                passed=not violations,
                violations=tuple(violations),
            )
        )

    eval_contract_ok = all(item.passed for item in eval_results)
    checks.append(
        Check(
            "d1_h4_evaluation_contract",
            "PASS" if eval_contract_ok else "FAIL",
            f"evaluations={len(eval_results)} violations={sum(not item.passed for item in eval_results)}",
        )
    )

    if eval_results:
        eval_webhook_status = "PASS" if edge_webhook_ok >= len(eval_results) else "FAIL"
        eval_webhook_detail = f"evaluations={len(eval_results)} edge_webhook_ok={edge_webhook_ok}"
    else:
        eval_webhook_status = "PENDING"
        eval_webhook_detail = "No H4 evaluation in the latest session yet."
    checks.append(Check("evaluation_webhook", eval_webhook_status, eval_webhook_detail))

    failed = any(check.status == "FAIL" for check in checks)
    if failed:
        status = "FAIL"
    elif not eval_results:
        status = "PASS_STARTUP_PENDING_EVALUATION"
    else:
        status = "PASS_PHASE1_FORWARD_GATE"

    return ValidationSummary(
        status=status,
        session_lines=len(session),
        expected_magic=expected_magic,
        observed_magic=observed_magic,
        evaluations=len(eval_results),
        edge_webhook_ok=edge_webhook_ok,
        checks=tuple(checks),
        evaluation_results=tuple(eval_results),
    )


def validate_paths(paths: Iterable[Path], expected_magic: int = 20260711) -> ValidationSummary:
    lines: list[str] = []
    for path in paths:
        lines.extend(read_log(path).splitlines())
    return validate_lines(lines, expected_magic=expected_magic)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--expected-magic", type=int, default=20260711)
    parser.add_argument("--require-evaluation", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    summary = validate_paths(args.logs, expected_magic=args.expected_magic)
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
