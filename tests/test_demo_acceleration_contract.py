from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from python.governance.demo_acceleration_contract import (
    load_contract,
    validate_contract,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "configs/demo_acceleration/demo_acceleration_v1.json"
CLI_PATH = ROOT / "python/pipeline/validate_demo_acceleration_contract.py"


class DemoAccelerationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract(CONTRACT_PATH)

    def test_canonical_contract_passes(self) -> None:
        result = validate_contract(self.contract)
        self.assertTrue(result.passed, result.errors)
        self.assertEqual(result.status, "PASS_GOVERNANCE_CONTRACT")
        self.assertEqual(result.engine_count, 5)
        self.assertEqual(result.planned_execution_count, 2)
        self.assertFalse(result.activation_authorized)
        self.assertEqual(len(result.contract_id), 24)

    def test_contract_identity_is_deterministic(self) -> None:
        first = validate_contract(self.contract)
        second = validate_contract(copy.deepcopy(self.contract))
        self.assertEqual(first.contract_id, second.contract_id)

    def test_stage1_cannot_authorize_activation(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["activation_authorized"] = True
        mutated["engines"]["sleeve_b_usdjpy_sell_touch025"]["activation_in_this_stage"] = True
        result = validate_contract(mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("activation_authorized" in error for error in result.errors))
        self.assertTrue(any("activation_in_this_stage" in error for error in result.errors))

    def test_control_risk_and_parameters_are_immutable(self) -> None:
        mutated = copy.deepcopy(self.contract)
        control = mutated["engines"]["stage10c_v4430_control"]
        control["initial_risk_pct"] = 0.5
        control["parameters_frozen"] = False
        result = validate_contract(mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("initial_risk_pct" in error for error in result.errors))
        self.assertTrue(any("parameters_frozen" in error for error in result.errors))

    def test_sleeve_b_stage10a_gate_cannot_be_replaced(self) -> None:
        mutated = copy.deepcopy(self.contract)
        gate = mutated["engines"]["sleeve_b_usdjpy_sell_touch025"]["continuity_gate"]
        gate["minimum_trades"] = 15
        gate["top3_share_strictly_less_than"] = 0.8
        gate["gate_replacement_allowed"] = True
        result = validate_contract(mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("minimum_trades" in error for error in result.errors))
        self.assertTrue(any("top3_share" in error for error in result.errors))
        self.assertTrue(any("gate_replacement_allowed" in error for error in result.errors))

    def test_frequency_challenger_may_change_only_body_c1(self) -> None:
        mutated = copy.deepcopy(self.contract)
        delta = mutated["engines"]["frequency_body015"]["parameter_delta"]
        delta["confirmation"] = {"control": 1.0, "challenger": 0.5}
        result = validate_contract(mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("must change body_c1_min and nothing else" in error for error in result.errors))

    def test_donchian_gate_cannot_be_replaced_by_generic_gate(self) -> None:
        mutated = copy.deepcopy(self.contract)
        gate = mutated["engines"]["stage10d_donchian"]["entry_gate"]
        gate["minimum_trades"] = 30
        gate["minimum_profit_factor_strictly_greater_than"] = 1.0
        gate["mandatory_condition_count"] = 0
        result = validate_contract(mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("minimum_trades" in error for error in result.errors))
        self.assertTrue(any("minimum_profit_factor" in error for error in result.errors))
        self.assertTrue(any("mandatory_condition_count" in error for error in result.errors))

    def test_experimental_accounts_and_identity_must_remain_isolated(self) -> None:
        mutated = copy.deepcopy(self.contract)
        sleeve = mutated["engines"]["sleeve_b_usdjpy_sell_touch025"]
        frequency = mutated["engines"]["frequency_body015"]
        sleeve["account_slot"] = "DEMO_C"
        sleeve["magic_number"] = frequency["magic_number"]
        sleeve["strategy_variant"] = frequency["strategy_variant"]
        result = validate_contract(mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("account_slot" in error for error in result.errors))
        self.assertTrue(any("unique magic_number" in error for error in result.errors))
        self.assertTrue(any("unique strategy_variant" in error for error in result.errors))

    def test_cli_passes_canonical_contract(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI_PATH), str(CONTRACT_PATH)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "PASS_GOVERNANCE_CONTRACT")
        self.assertFalse(payload["activation_authorized"])


if __name__ == "__main__":
    unittest.main()
