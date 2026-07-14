"""Govern Stage10D Phase 2 gaps without mutating raw data quality evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Optional

from python.research.stage10d_data_readiness import TIMEFRAME_SECONDS, audit_rows


@dataclass(frozen=True)
class GovernedGapDecision:
    rule_id: str
    timeframe: str
    previous_time: str
    current_time: str
    classification: str
    action: str
    missing_bar_times: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class GapGovernanceReport:
    symbol: str
    timeframe: str
    raw_quality_status: str
    status: str
    structural_violation_count: int
    confirmed_session_gap_count: int
    governed_gap_count: int
    pending_calendar_gap_count: int
    unmatched_gap_count: int
    confirmed_session_gaps: tuple[GovernedGapDecision, ...]
    governed_gaps: tuple[GovernedGapDecision, ...]
    pending_calendar_gaps: tuple[GovernedGapDecision, ...]
    unmatched_gaps: tuple[dict[str, object], ...]


def load_json_object(path: Path, *, label: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def load_gap_policy(path: Path) -> dict[str, object]:
    payload = load_json_object(path, label="Gap policy")
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Gap policy field 'rules' must be a list")
    return payload


def load_feed_profile(path: Path) -> dict[str, object]:
    return load_json_object(path, label="Feed profile")


def _canonical_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _gap_key(timeframe: str, previous_time: str, current_time: str) -> tuple[str, str, str]:
    return timeframe.upper(), previous_time, current_time


def _missing_bar_times(previous: str, current: str, timeframe: str) -> tuple[str, ...]:
    step = timedelta(seconds=TIMEFRAME_SECONDS[timeframe.upper()])
    previous_dt = datetime.strptime(previous, "%Y-%m-%d %H:%M:%S")
    current_dt = datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
    values: list[str] = []
    candidate = previous_dt + step
    while candidate < current_dt:
        values.append(_canonical_time(candidate))
        candidate += step
    return tuple(values)


def _feed_profile_promotes_pending(
    *,
    feed_profile: Optional[Mapping[str, object]],
    policy: Mapping[str, object],
    symbol: str,
) -> bool:
    if feed_profile is None:
        return False

    profile_symbol = str(feed_profile.get("symbol", "")).upper()
    if profile_symbol and profile_symbol != symbol.upper():
        raise ValueError(
            f"Feed profile symbol mismatch: expected {symbol.upper()} observed {profile_symbol}"
        )

    confirmation = feed_profile.get("calendar_confirmation")
    if not isinstance(confirmation, Mapping):
        return False
    if confirmation.get("mode") != "PROMOTE_EXACT_ENUMERATED_PENDING_RULES":
        return False

    allowed_versions = confirmation.get("allowed_policy_versions", [])
    if not isinstance(allowed_versions, list):
        raise ValueError("Feed profile allowed_policy_versions must be a list")
    policy_version = str(policy.get("policy_version", ""))
    return policy_version in {str(value) for value in allowed_versions}


def evaluate_gap_governance(
    rows: Iterable[Mapping[str, object]],
    *,
    symbol: str,
    timeframe: str,
    policy: Mapping[str, object],
    feed_profile: Optional[Mapping[str, object]] = None,
) -> GapGovernanceReport:
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    policy_symbol = str(policy.get("symbol", "")).upper()
    if policy_symbol and policy_symbol != symbol.upper():
        raise ValueError(
            f"Gap policy symbol mismatch: expected {symbol.upper()} observed {policy_symbol}"
        )

    promote_pending = _feed_profile_promotes_pending(
        feed_profile=feed_profile,
        policy=policy,
        symbol=symbol,
    )

    quality = audit_rows(rows, timeframe=timeframe)
    structural_violation_count = sum(
        (
            quality.duplicate_count,
            quality.source_order_violation_count,
            quality.ohlc_violation_count,
            quality.nonpositive_volume_count,
            quality.unknown_gap_count,
        )
    )

    rules_by_key: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for rule in policy.get("rules", []):
        if not isinstance(rule, Mapping):
            continue
        key = _gap_key(
            str(rule.get("timeframe", "")),
            str(rule.get("previous_time", "")),
            str(rule.get("current_time", "")),
        )
        if key in rules_by_key:
            raise ValueError(f"Duplicate gap policy rule for {key}")
        rules_by_key[key] = rule

    confirmed_session: list[GovernedGapDecision] = []
    governed: list[GovernedGapDecision] = []
    pending: list[GovernedGapDecision] = []
    unmatched: list[dict[str, object]] = []

    for gap in quality.gaps:
        if gap.classification == "expected_market_closure":
            continue
        key = _gap_key(timeframe, gap.previous_time, gap.current_time)
        rule = rules_by_key.get(key)
        if rule is None:
            unmatched.append(asdict(gap))
            continue

        classification = str(rule.get("classification", ""))
        action = str(rule.get("action", ""))
        rationale = str(rule.get("rationale", ""))
        if classification == "PENDING_BROKER_CALENDAR_CONFIRMATION" and promote_pending:
            classification = "CONFIRMED_SOURCE_SESSION_CLOSURE"
            action = "ALLOW_EXACT_SESSION_GAP_NO_SYNTHETIC_BARS"
            rationale = (
                rationale
                + " Promoted only for this exact enumerated interval by the verified feed profile; "
                "no generic calendar or historical UTC offset is inferred."
            )

        decision = GovernedGapDecision(
            rule_id=str(rule.get("rule_id", "")),
            timeframe=timeframe,
            previous_time=gap.previous_time,
            current_time=gap.current_time,
            classification=classification,
            action=action,
            missing_bar_times=_missing_bar_times(
                gap.previous_time,
                gap.current_time,
                timeframe,
            ),
            rationale=rationale,
        )
        if decision.classification == "CONFIRMED_SOURCE_SESSION_CLOSURE":
            confirmed_session.append(decision)
        elif decision.classification == "GOVERNED_DATA_GAP":
            governed.append(decision)
        elif decision.classification == "PENDING_BROKER_CALENDAR_CONFIRMATION":
            pending.append(decision)
        else:
            unmatched.append(asdict(gap))

    if structural_violation_count:
        status = "FAIL_STRUCTURAL"
    elif unmatched:
        status = "FAIL_UNGOVERNED_GAPS"
    elif pending:
        status = "PENDING_BROKER_CALENDAR"
    elif governed and confirmed_session:
        status = "PASS_WITH_SESSION_CLOSURES_AND_GOVERNED_EXCLUSIONS"
    elif governed:
        status = "PASS_WITH_GOVERNED_EXCLUSIONS"
    elif confirmed_session:
        status = "PASS_WITH_CONFIRMED_SESSION_CLOSURES"
    else:
        status = "PASS"

    return GapGovernanceReport(
        symbol=symbol.upper(),
        timeframe=timeframe,
        raw_quality_status=quality.status,
        status=status,
        structural_violation_count=structural_violation_count,
        confirmed_session_gap_count=len(confirmed_session),
        governed_gap_count=len(governed),
        pending_calendar_gap_count=len(pending),
        unmatched_gap_count=len(unmatched),
        confirmed_session_gaps=tuple(confirmed_session),
        governed_gaps=tuple(governed),
        pending_calendar_gaps=tuple(pending),
        unmatched_gaps=tuple(unmatched),
    )
