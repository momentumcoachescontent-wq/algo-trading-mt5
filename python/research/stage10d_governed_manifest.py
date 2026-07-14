"""Build auditable Stage10D Phase 2 governed dataset manifests.

The raw parser/auditor remains the source of truth for physical CSV quality. This
module layers an explicit gap policy and verified feed profile on top without
mutating raw rows or silently converting broker-server timestamps.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

from python.research.stage10d_data_readiness import (
    ReadinessBundle,
    build_readiness_bundle,
    sha256_file,
)
from python.research.stage10d_gap_governance import (
    GapGovernanceReport,
    evaluate_gap_governance,
    load_feed_profile,
    load_gap_policy,
)

GOVERNED_MANIFEST_VERSION = "stage10d-governed-data-manifest-v1"
PASSING_GOVERNANCE_STATUSES = {
    "PASS",
    "PASS_WITH_CONFIRMED_SESSION_CLOSURES",
    "PASS_WITH_GOVERNED_EXCLUSIONS",
    "PASS_WITH_SESSION_CLOSURES_AND_GOVERNED_EXCLUSIONS",
}


@dataclass(frozen=True)
class GovernedDatasetManifest:
    manifest_version: str
    governed_manifest_id: str
    generated_at_utc: str
    raw_data_manifest_id: str
    parser_version: str
    source_file: str
    source_sha256: str
    source_size_bytes: int
    policy_version: str
    policy_sha256: str
    feed_profile_version: str
    feed_profile_sha256: str
    broker_company: str
    account_server: str
    terminal_environment: str
    symbol: str
    timeframe: str
    timestamp_semantics: str
    observed_server_offset: str
    offset_observed_at_utc: str
    historical_offset_policy: str
    synthetic: bool
    row_count: int
    first_bar_time: Optional[str]
    last_bar_time: Optional[str]
    coverage_classification: str
    raw_quality_status: str
    governance_status: str
    research_eligible: bool
    structural_violation_count: int
    expected_market_closure_gap_count: int
    confirmed_session_gap_count: int
    governed_data_gap_count: int
    pending_calendar_gap_count: int
    unmatched_gap_count: int
    excluded_bar_times: tuple[str, ...]
    exclusion_policy: str
    session_closure_policy: str


@dataclass(frozen=True)
class GovernedManifestBundle:
    readiness: ReadinessBundle
    governance: GapGovernanceReport
    manifest: GovernedDatasetManifest


def _manifest_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _require_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"Feed profile field '{key}' is required")
    return value


def _coverage_classification(timeframe: str) -> str:
    return (
        "PARTIAL_INTRABAR_PATH_COVERAGE"
        if timeframe.upper() == "M15"
        else "PRIMARY_CANONICAL_BAR_HISTORY"
    )


def build_governed_manifest_bundle(
    csv_path: Path,
    *,
    policy_path: Path,
    feed_profile_path: Path,
    symbol: str,
    timeframe: str,
    export_timestamp_utc: Optional[str] = None,
) -> GovernedManifestBundle:
    policy = load_gap_policy(policy_path)
    feed_profile = load_feed_profile(feed_profile_path)

    broker_company = _require_text(feed_profile, "broker_company")
    account_server = _require_text(feed_profile, "account_server")
    terminal_environment = _require_text(feed_profile, "terminal_environment")
    profile_symbol = str(feed_profile.get("symbol", "")).upper()
    if profile_symbol and profile_symbol != symbol.upper():
        raise ValueError(
            f"Feed profile symbol mismatch: expected {symbol.upper()} observed {profile_symbol}"
        )

    observation = feed_profile.get("server_time_observation")
    if not isinstance(observation, Mapping):
        raise ValueError("Feed profile field 'server_time_observation' must be an object")
    observed_offset = _require_text(observation, "offset")
    observed_at_utc = _require_text(observation, "observed_at_utc")
    historical_offset_policy = _require_text(feed_profile, "historical_offset_policy")

    timestamp_semantics = (
        f"{account_server} broker-server wall-clock; observed {observed_offset} at "
        f"{observed_at_utc}; no historical UTC conversion inferred"
    )
    readiness = build_readiness_bundle(
        csv_path,
        symbol=symbol,
        timeframe=timeframe,
        broker=broker_company,
        terminal=terminal_environment,
        server_timezone=timestamp_semantics,
        export_timestamp_utc=export_timestamp_utc,
    )
    governance = evaluate_gap_governance(
        readiness.rows,
        symbol=symbol,
        timeframe=timeframe,
        policy=policy,
        feed_profile=feed_profile,
    )

    policy_version = str(policy.get("policy_version", "")).strip()
    profile_version = str(feed_profile.get("profile_version", "")).strip()
    if not policy_version:
        raise ValueError("Gap policy field 'policy_version' is required")
    if not profile_version:
        raise ValueError("Feed profile field 'profile_version' is required")

    excluded_bar_times = tuple(
        sorted(
            {
                bar_time
                for gap in governance.governed_gaps
                for bar_time in gap.missing_bar_times
            }
        )
    )
    policy_hash = sha256_file(policy_path)
    profile_hash = sha256_file(feed_profile_path)
    research_eligible = governance.status in PASSING_GOVERNANCE_STATUSES

    identity = {
        "manifest_version": GOVERNED_MANIFEST_VERSION,
        "raw_data_manifest_id": readiness.manifest.data_manifest_id,
        "source_sha256": readiness.manifest.source_sha256,
        "policy_version": policy_version,
        "policy_sha256": policy_hash,
        "feed_profile_version": profile_version,
        "feed_profile_sha256": profile_hash,
        "broker_company": broker_company,
        "account_server": account_server,
        "terminal_environment": terminal_environment,
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "timestamp_semantics": timestamp_semantics,
        "synthetic": False,
        "coverage_classification": _coverage_classification(timeframe),
        "governance_status": governance.status,
        "excluded_bar_times": excluded_bar_times,
    }

    manifest = GovernedDatasetManifest(
        manifest_version=GOVERNED_MANIFEST_VERSION,
        governed_manifest_id=_manifest_id(identity),
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        raw_data_manifest_id=readiness.manifest.data_manifest_id,
        parser_version=readiness.manifest.parser_version,
        source_file=str(csv_path),
        source_sha256=readiness.manifest.source_sha256,
        source_size_bytes=readiness.manifest.source_size_bytes,
        policy_version=policy_version,
        policy_sha256=policy_hash,
        feed_profile_version=profile_version,
        feed_profile_sha256=profile_hash,
        broker_company=broker_company,
        account_server=account_server,
        terminal_environment=terminal_environment,
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        timestamp_semantics=timestamp_semantics,
        observed_server_offset=observed_offset,
        offset_observed_at_utc=observed_at_utc,
        historical_offset_policy=historical_offset_policy,
        synthetic=False,
        row_count=readiness.manifest.row_count,
        first_bar_time=readiness.manifest.first_bar_time,
        last_bar_time=readiness.manifest.last_bar_time,
        coverage_classification=_coverage_classification(timeframe),
        raw_quality_status=readiness.quality.status,
        governance_status=governance.status,
        research_eligible=research_eligible,
        structural_violation_count=governance.structural_violation_count,
        expected_market_closure_gap_count=(
            readiness.quality.expected_market_closure_gap_count
        ),
        confirmed_session_gap_count=governance.confirmed_session_gap_count,
        governed_data_gap_count=governance.governed_gap_count,
        pending_calendar_gap_count=governance.pending_calendar_gap_count,
        unmatched_gap_count=governance.unmatched_gap_count,
        excluded_bar_times=excluded_bar_times,
        exclusion_policy=(
            "EXCLUDE_ANY_ANALYTIC_WINDOW_CROSSING_GOVERNED_DATA_GAP"
        ),
        session_closure_policy=(
            "ALLOW_ONLY_EXACT_INTERVALS_ENUMERATED_BY_POLICY_AND_VERIFIED_FEED_PROFILE"
        ),
    )
    return GovernedManifestBundle(
        readiness=readiness,
        governance=governance,
        manifest=manifest,
    )


def write_governed_manifest_bundle(
    bundle: GovernedManifestBundle,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{bundle.manifest.symbol.lower()}_{bundle.manifest.timeframe.lower()}_"
        f"{bundle.manifest.governed_manifest_id}"
    )
    governed_manifest_path = output_dir / f"{stem}_governed_manifest.json"
    raw_manifest_path = output_dir / f"{stem}_raw_manifest.json"
    raw_quality_path = output_dir / f"{stem}_raw_quality.json"
    governance_path = output_dir / f"{stem}_gap_governance.json"

    governed_manifest_path.write_text(
        json.dumps(asdict(bundle.manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raw_manifest_path.write_text(
        json.dumps(asdict(bundle.readiness.manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raw_quality_path.write_text(
        json.dumps(asdict(bundle.readiness.quality), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    governance_path.write_text(
        json.dumps(asdict(bundle.governance), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "governed_manifest": governed_manifest_path,
        "raw_manifest": raw_manifest_path,
        "raw_quality": raw_quality_path,
        "gap_governance": governance_path,
    }
