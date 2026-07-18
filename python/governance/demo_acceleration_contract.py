"""Validate the Demo Acceleration governance contract.

Standard-library only. This module validates governance and identity decisions; it
cannot activate an EA, change risk, send an order, or write to production systems.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

PROGRAM_VERSION = "demo-acceleration-governance-v1"
EXPECTED_ENGINE_IDENTITIES: dict[str, dict[str, Any]] = {
    "stage10c_v4430_control": {
        "strategy_variant": "stage10c_v4430_usdjpy_control",
        "execution_mode": "DEMO_EXECUTION_CONTROL",
        "magic_number": 20260527,
        "guard_version": "v4430_stage10c_control",
    },
    "stage10c_v4431_d1_shadow": {
        "strategy_variant": "stage10c_v4431_d1_context_integrity",
        "execution_mode": "SHADOW_ONLY",
        "magic_number": 20260711,
        "guard_version": "v4431_d1_context_integrity",
    },
    "sleeve_b_usdjpy_sell_touch025": {
        "strategy_variant": "stage10b_usdjpy_sell_touch025_demo",
        "execution_mode": "DEMO_EXPERIMENTAL_PLANNED",
        "magic_number": 20260721,
        "guard_version": "stage10a_sleeve_b_gate_v1",
    },
    "frequency_body015": {
        "strategy_variant": "stage10c_usdjpy_body015_demo",
        "execution_mode": "DEMO_EXPERIMENTAL_PLANNED",
        "magic_number": 20260722,
        "guard_version": "stage10c_frequency_body015_v1",
    },
    "stage10d_donchian": {
        "strategy_variant": "stage10d_donchian_research",
        "execution_mode": "OFFLINE_ONLY",
        "magic_number": 20260723,
        "guard_version": "stage10d_research_gate_v1",
    },
}
EXPECTED_ENGINE_IDS = set(EXPECTED_ENGINE_IDENTITIES)
REQUIRED_IDENTITY_FIELDS = {
    "experiment_id",
    "strategy_variant",
    "execution_mode",
    "magic_number",
    "guard_version",
    "risk_pct",
    "config_hash",
    "code_commit_sha",
}
REQUIRED_CONTROL_FROZEN_FIELDS = {
    "ema_period",
    "adx_min",
    "body_c1_min",
    "confirmation",
    "sl_atr",
    "tp_atr",
    "sessions",
    "friday_guard",
    "governance",
}
REQUIRED_FREQUENCY_UNCHANGED_FIELDS = {
    "ema_period",
    "d1_context",
    "adx_min",
    "confirmation",
    "sessions",
    "sl_atr",
    "tp_atr",
    "friday_guard",
    "governance",
}
REQUIRED_STAGE1_EXIT_CRITERIA = {
    "machine_readable_contract_validates",
    "control_parameters_and_risk_are_frozen",
    "challenger_specific_gates_are_preserved",
    "no_new_execution_is_authorized",
    "account_and_identity_isolation_is_defined",
    "portfolio_risk_limits_are_defined",
    "future_branch_boundaries_are_defined",
}


@dataclass(frozen=True)
class ContractValidation:
    status: str
    contract_id: str
    errors: tuple[str, ...]
    engine_count: int
    planned_execution_count: int
    activation_authorized: bool

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_id": self.contract_id,
            "errors": list(self.errors),
            "engine_count": self.engine_count,
            "planned_execution_count": self.planned_execution_count,
            "activation_authorized": self.activation_authorized,
        }


def load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("demo acceleration contract must be a JSON object")
    return payload


def canonical_contract_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _as_mapping(value: Any, path: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _as_string_set(value: Any, path: str, errors: list[str]) -> set[str]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return set()
    if any(not isinstance(item, str) for item in value):
        errors.append(f"{path} must contain only strings")
        return set()
    return set(value)


def _require_equal(observed: Any, expected: Any, path: str, errors: list[str]) -> None:
    if observed != expected:
        errors.append(f"{path} must equal {expected!r}; observed {observed!r}")


def _require_true(observed: Any, path: str, errors: list[str]) -> None:
    _require_equal(observed, True, path, errors)


def _require_false(observed: Any, path: str, errors: list[str]) -> None:
    _require_equal(observed, False, path, errors)


def _validate_global(payload: Mapping[str, Any], errors: list[str]) -> None:
    _require_equal(payload.get("program_version"), PROGRAM_VERSION, "program_version", errors)
    _require_equal(payload.get("program_status"), "GOVERNANCE_ONLY", "program_status", errors)
    _require_equal(payload.get("environment"), "DEMO", "environment", errors)
    _require_false(payload.get("activation_authorized"), "activation_authorized", errors)
    _require_false(
        payload.get("production_capital_authorized"),
        "production_capital_authorized",
        errors,
    )
    _require_equal(payload.get("symbol_scope"), ["USDJPY"], "symbol_scope", errors)

    if _as_string_set(
        payload.get("required_identity_fields"),
        "required_identity_fields",
        errors,
    ) != REQUIRED_IDENTITY_FIELDS:
        errors.append(
            "required_identity_fields must exactly preserve the approved audit identity"
        )

    if _as_string_set(
        payload.get("stage1_exit_criteria"),
        "stage1_exit_criteria",
        errors,
    ) != REQUIRED_STAGE1_EXIT_CRITERIA:
        errors.append(
            "stage1_exit_criteria must exactly match the approved Stage 1 closure set"
        )

    limits = _as_mapping(payload.get("global_risk_limits"), "global_risk_limits", errors)
    expected_limits = {
        "max_experimental_open_risk_pct": 2.0,
        "max_same_direction_usdjpy_risk_pct": 1.25,
        "max_experimental_positions": 3,
        "daily_new_entry_block_pct": 2.5,
        "weekly_program_pause_pct": 5.0,
        "program_drawdown_stop_pct": 7.0,
    }
    for key, expected in expected_limits.items():
        _require_equal(limits.get(key), expected, f"global_risk_limits.{key}", errors)


def _validate_common_engine(
    engine_id: str,
    engine: Mapping[str, Any],
    errors: list[str],
) -> None:
    prefix = f"engines.{engine_id}"
    for field, expected in EXPECTED_ENGINE_IDENTITIES[engine_id].items():
        _require_equal(engine.get(field), expected, f"{prefix}.{field}", errors)
    _require_false(
        engine.get("activation_in_this_stage"),
        f"{prefix}.activation_in_this_stage",
        errors,
    )


def _validate_control(engine: Mapping[str, Any], errors: list[str]) -> None:
    prefix = "engines.stage10c_v4430_control"
    _require_equal(engine.get("role"), "CONTROL", f"{prefix}.role", errors)
    _require_equal(
        engine.get("lifecycle_status"),
        "EXISTING_DEMO_CONTROL",
        f"{prefix}.lifecycle_status",
        errors,
    )
    _require_equal(engine.get("account_slot"), "DEMO_A", f"{prefix}.account_slot", errors)
    _require_equal(engine.get("initial_risk_pct"), 0.25, f"{prefix}.initial_risk_pct", errors)
    _require_equal(engine.get("max_risk_pct"), 0.25, f"{prefix}.max_risk_pct", errors)
    _require_true(engine.get("parameters_frozen"), f"{prefix}.parameters_frozen", errors)
    if _as_string_set(
        engine.get("frozen_fields"),
        f"{prefix}.frozen_fields",
        errors,
    ) != REQUIRED_CONTROL_FROZEN_FIELDS:
        errors.append(f"{prefix}.frozen_fields must preserve the complete control parameter set")


def _validate_d1_shadow(engine: Mapping[str, Any], errors: list[str]) -> None:
    prefix = "engines.stage10c_v4431_d1_shadow"
    _require_false(engine.get("order_send_allowed"), f"{prefix}.order_send_allowed", errors)
    _require_equal(engine.get("initial_risk_pct"), 0.0, f"{prefix}.initial_risk_pct", errors)
    _require_equal(engine.get("max_risk_pct"), 0.0, f"{prefix}.max_risk_pct", errors)
    _require_false(
        engine.get("economic_performance_measurable"),
        f"{prefix}.economic_performance_measurable",
        errors,
    )
    _require_equal(
        engine.get("required_future_capability"),
        "SHADOW_TRADE_LEDGER",
        f"{prefix}.required_future_capability",
        errors,
    )


def _validate_sleeve_b(engine: Mapping[str, Any], errors: list[str]) -> None:
    prefix = "engines.sleeve_b_usdjpy_sell_touch025"
    _require_equal(
        engine.get("lifecycle_status"),
        "PLANNED_NOT_AUTHORIZED",
        f"{prefix}.lifecycle_status",
        errors,
    )
    _require_false(engine.get("order_send_allowed", False), f"{prefix}.order_send_allowed", errors)
    _require_equal(engine.get("account_slot"), "DEMO_B", f"{prefix}.account_slot", errors)
    _require_equal(engine.get("direction_scope"), "SELL", f"{prefix}.direction_scope", errors)
    _require_equal(engine.get("initial_risk_pct"), 0.5, f"{prefix}.initial_risk_pct", errors)
    _require_equal(engine.get("max_risk_pct"), 0.75, f"{prefix}.max_risk_pct", errors)
    _require_equal(
        engine.get("risk_escalation_requires_clean_trades"),
        5,
        f"{prefix}.risk_escalation_requires_clean_trades",
        errors,
    )

    gate = _as_mapping(engine.get("continuity_gate"), f"{prefix}.continuity_gate", errors)
    expected_gate = {
        "gate_owner": "STAGE10A",
        "gate_replacement_allowed": False,
        "minimum_forward_weeks": 16,
        "minimum_trades": 30,
        "median_r_strictly_greater_than": 0.0,
        "top3_share_strictly_less_than": 0.4,
    }
    for key, expected in expected_gate.items():
        _require_equal(gate.get(key), expected, f"{prefix}.continuity_gate.{key}", errors)


def _validate_frequency(engine: Mapping[str, Any], errors: list[str]) -> None:
    prefix = "engines.frequency_body015"
    _require_equal(
        engine.get("lifecycle_status"),
        "PLANNED_NOT_AUTHORIZED",
        f"{prefix}.lifecycle_status",
        errors,
    )
    _require_false(engine.get("order_send_allowed", False), f"{prefix}.order_send_allowed", errors)
    _require_equal(engine.get("account_slot"), "DEMO_C", f"{prefix}.account_slot", errors)
    _require_equal(engine.get("initial_risk_pct"), 0.5, f"{prefix}.initial_risk_pct", errors)
    _require_equal(engine.get("max_risk_pct"), 0.75, f"{prefix}.max_risk_pct", errors)

    delta = _as_mapping(engine.get("parameter_delta"), f"{prefix}.parameter_delta", errors)
    if set(delta) != {"body_c1_min"}:
        errors.append(f"{prefix}.parameter_delta must change body_c1_min and nothing else")
    body_delta = _as_mapping(
        delta.get("body_c1_min"),
        f"{prefix}.parameter_delta.body_c1_min",
        errors,
    )
    _require_equal(body_delta.get("control"), 0.25, f"{prefix}.parameter_delta.body_c1_min.control", errors)
    _require_equal(body_delta.get("challenger"), 0.15, f"{prefix}.parameter_delta.body_c1_min.challenger", errors)

    if _as_string_set(
        engine.get("required_unchanged_fields"),
        f"{prefix}.required_unchanged_fields",
        errors,
    ) != REQUIRED_FREQUENCY_UNCHANGED_FIELDS:
        errors.append(
            f"{prefix}.required_unchanged_fields must preserve every non-body causal field"
        )

    technical = _as_mapping(engine.get("technical_checkpoint"), f"{prefix}.technical_checkpoint", errors)
    _require_equal(technical.get("minimum_trades"), 8, f"{prefix}.technical_checkpoint.minimum_trades", errors)
    _require_equal(
        technical.get("purpose"),
        "CONTINUE_TECHNICAL_VALIDATION_ONLY",
        f"{prefix}.technical_checkpoint.purpose",
        errors,
    )

    provisional = _as_mapping(engine.get("provisional_checkpoint"), f"{prefix}.provisional_checkpoint", errors)
    _require_equal(provisional.get("minimum_trades"), 15, f"{prefix}.provisional_checkpoint.minimum_trades", errors)
    _require_equal(
        provisional.get("purpose"),
        "CONTINUE_DEMO_ONLY",
        f"{prefix}.provisional_checkpoint.purpose",
        errors,
    )

    strong = _as_mapping(engine.get("proposed_strong_gate"), f"{prefix}.proposed_strong_gate", errors)
    _require_equal(
        strong.get("gate_status"),
        "PROPOSED_REQUIRES_SEPARATE_APPROVAL",
        f"{prefix}.proposed_strong_gate.gate_status",
        errors,
    )
    _require_equal(strong.get("minimum_trades"), 30, f"{prefix}.proposed_strong_gate.minimum_trades", errors)
    _require_equal(strong.get("top3_share_strictly_less_than"), 0.4, f"{prefix}.proposed_strong_gate.top3_share_strictly_less_than", errors)
    _require_true(strong.get("out_of_sample_required"), f"{prefix}.proposed_strong_gate.out_of_sample_required", errors)


def _validate_donchian(engine: Mapping[str, Any], errors: list[str]) -> None:
    prefix = "engines.stage10d_donchian"
    _require_equal(
        engine.get("lifecycle_status"),
        "OFFLINE_RESEARCH_ONLY",
        f"{prefix}.lifecycle_status",
        errors,
    )
    _require_false(engine.get("order_send_allowed"), f"{prefix}.order_send_allowed", errors)
    _require_equal(engine.get("initial_risk_pct"), 0.0, f"{prefix}.initial_risk_pct", errors)
    _require_equal(engine.get("max_risk_pct"), 0.0, f"{prefix}.max_risk_pct", errors)
    _require_equal(
        engine.get("demo_execution_block"),
        "BLOCKED_UNTIL_FULL_ENTRY_GATE_PASS",
        f"{prefix}.demo_execution_block",
        errors,
    )

    gate = _as_mapping(engine.get("entry_gate"), f"{prefix}.entry_gate", errors)
    expected_gate = {
        "gate_owner": "STAGE10D_APPROVED_2026_07_10",
        "gate_replacement_allowed": False,
        "minimum_trades": 80,
        "minimum_profit_factor_strictly_greater_than": 1.15,
        "out_of_sample_required": True,
        "mandatory_condition_count": 4,
        "mandatory_conditions_source": "APPROVED_2026_07_10_DECISION_AND_STAGE10D_CHARTER",
        "all_mandatory_conditions_required": True,
    }
    for key, expected in expected_gate.items():
        _require_equal(gate.get(key), expected, f"{prefix}.entry_gate.{key}", errors)

    data = _as_mapping(engine.get("canonical_data"), f"{prefix}.canonical_data", errors)
    _require_equal(data.get("source"), "MetaQuotes-Demo MT5 CSV", f"{prefix}.canonical_data.source", errors)
    _require_true(data.get("governed_gap_windows_excluded"), f"{prefix}.canonical_data.governed_gap_windows_excluded", errors)
    _require_false(data.get("synthetic_promotion_evidence_allowed"), f"{prefix}.canonical_data.synthetic_promotion_evidence_allowed", errors)


def _validate_isolation(
    payload: Mapping[str, Any],
    engines: Mapping[str, Any],
    errors: list[str],
) -> None:
    isolation = _as_mapping(payload.get("isolation_rules"), "isolation_rules", errors)
    expected_isolation = {
        "separate_accounts_preferred": True,
        "shared_netting_account_for_experimental_engines_allowed": False,
        "unique_magic_numbers_required": True,
        "unique_strategy_variants_required": True,
        "cross_engine_position_adoption_allowed": False,
        "manual_discretionary_intervention_allowed": False,
    }
    for key, expected in expected_isolation.items():
        _require_equal(isolation.get(key), expected, f"isolation_rules.{key}", errors)

    magic_numbers = [
        engine.get("magic_number")
        for engine in engines.values()
        if isinstance(engine, Mapping) and engine.get("magic_number") is not None
    ]
    if len(magic_numbers) != len(set(magic_numbers)):
        errors.append("every engine must have a unique magic_number")

    variants = [
        engine.get("strategy_variant")
        for engine in engines.values()
        if isinstance(engine, Mapping) and engine.get("strategy_variant") is not None
    ]
    if len(variants) != len(set(variants)):
        errors.append("every engine must have a unique strategy_variant")

    expected_accounts = {
        "stage10c_v4430_control": "DEMO_A",
        "stage10c_v4431_d1_shadow": "DEMO_A",
        "sleeve_b_usdjpy_sell_touch025": "DEMO_B",
        "frequency_body015": "DEMO_C",
        "stage10d_donchian": "UNASSIGNED",
    }
    for engine_id, expected_account in expected_accounts.items():
        engine = engines.get(engine_id, {})
        if isinstance(engine, Mapping):
            _require_equal(
                engine.get("account_slot"),
                expected_account,
                f"engines.{engine_id}.account_slot",
                errors,
            )

    branches = _as_mapping(payload.get("future_branch_boundaries"), "future_branch_boundaries", errors)
    branch_values = list(branches.values())
    if len(branch_values) != len(set(branch_values)):
        errors.append("future_branch_boundaries must be unique")


def validate_contract(payload: Mapping[str, Any]) -> ContractValidation:
    errors: list[str] = []
    _validate_global(payload, errors)

    engines = _as_mapping(payload.get("engines"), "engines", errors)
    if set(engines) != EXPECTED_ENGINE_IDS:
        errors.append("engines must exactly match the approved control and challenger set")

    validated: dict[str, Mapping[str, Any]] = {}
    for engine_id in EXPECTED_ENGINE_IDS:
        engine = _as_mapping(engines.get(engine_id), f"engines.{engine_id}", errors)
        validated[engine_id] = engine
        _validate_common_engine(engine_id, engine, errors)

    _validate_control(validated["stage10c_v4430_control"], errors)
    _validate_d1_shadow(validated["stage10c_v4431_d1_shadow"], errors)
    _validate_sleeve_b(validated["sleeve_b_usdjpy_sell_touch025"], errors)
    _validate_frequency(validated["frequency_body015"], errors)
    _validate_donchian(validated["stage10d_donchian"], errors)
    _validate_isolation(payload, engines, errors)

    planned_execution_count = sum(
        1
        for engine in engines.values()
        if isinstance(engine, Mapping)
        and engine.get("lifecycle_status") == "PLANNED_NOT_AUTHORIZED"
    )
    unique_errors = tuple(dict.fromkeys(errors))
    return ContractValidation(
        status="PASS_GOVERNANCE_CONTRACT" if not unique_errors else "FAIL_GOVERNANCE_CONTRACT",
        contract_id=canonical_contract_id(payload),
        errors=unique_errors,
        engine_count=len(engines),
        planned_execution_count=planned_execution_count,
        activation_authorized=bool(payload.get("activation_authorized")),
    )
