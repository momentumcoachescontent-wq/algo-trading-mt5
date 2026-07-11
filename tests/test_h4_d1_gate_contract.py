import unittest

from python.research.h4_d1_gate_contract import gate_h4_signal


class H4D1GateContractTests(unittest.TestCase):
    def test_neutral_bias_blocks_raw_buy(self):
        decision = gate_h4_signal(1, 0)
        self.assertEqual(decision.filtered_signal, 0)
        self.assertEqual(decision.reason, "d1_neutral_blocks_h4_signal")

    def test_neutral_bias_blocks_raw_sell(self):
        decision = gate_h4_signal(-1, 0)
        self.assertEqual(decision.filtered_signal, 0)
        self.assertEqual(decision.reason, "d1_neutral_blocks_h4_signal")

    def test_opposite_bias_blocks_candidate(self):
        self.assertEqual(gate_h4_signal(1, -1).filtered_signal, 0)
        self.assertEqual(gate_h4_signal(-1, 1).filtered_signal, 0)
        self.assertEqual(
            gate_h4_signal(1, -1).reason,
            "d1_bias_blocks_opposite_h4_signal",
        )

    def test_aligned_candidate_is_promoted(self):
        self.assertEqual(gate_h4_signal(1, 1).filtered_signal, 1)
        self.assertEqual(gate_h4_signal(-1, -1).filtered_signal, -1)

    def test_snapshot_mismatch_always_fails_closed(self):
        decision = gate_h4_signal(1, 1, snapshot_match=False)
        self.assertEqual(decision.filtered_signal, 0)
        self.assertEqual(decision.reason, "d1_context_snapshot_mismatch")

    def test_no_pattern_remains_zero(self):
        decision = gate_h4_signal(0, 1)
        self.assertEqual(decision.filtered_signal, 0)
        self.assertEqual(decision.reason, "no_h4_pattern")

    def test_invalid_inputs_fail(self):
        with self.assertRaises(ValueError):
            gate_h4_signal(2, 1)
        with self.assertRaises(ValueError):
            gate_h4_signal(1, 2)


if __name__ == "__main__":
    unittest.main()