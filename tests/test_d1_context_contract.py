import unittest

from python.research.d1_context_contract import (
    D1Alignment,
    D1ContextSnapshot,
    D1Reason,
    check_bias_synchronization,
    specific_block_reason,
)


def bullish_snapshot(structure: int, has_structure: bool = True) -> D1ContextSnapshot:
    return D1ContextSnapshot(
        symbol="USDJPY",
        d1_bar="2026.07.08",
        structure=structure,
        has_structure=has_structure,
        ema_rising=True,
        ema_falling=False,
        d1_above_ema=True,
        d1_below_ema=False,
        h4_above_ema=True,
        h4_below_ema=False,
        weighted_bias=0.4,
        ema_component=1.0,
        donchian_component=1.0,
    )


class D1ContextContractTests(unittest.TestCase):
    def test_bullish_components_with_bull_structure_are_aligned(self):
        snapshot = bullish_snapshot(1)
        self.assertEqual(snapshot.discrete_bias, 1)
        self.assertEqual(snapshot.alignment, D1Alignment.ALIGNED)
        self.assertEqual(snapshot.reason, D1Reason.BULL_ALIGNED)

    def test_bullish_components_without_structure_remain_bullish(self):
        snapshot = bullish_snapshot(0, has_structure=False)
        self.assertEqual(snapshot.discrete_bias, 1)
        self.assertEqual(snapshot.alignment, D1Alignment.PARTIALLY_ALIGNED)
        self.assertEqual(snapshot.reason, D1Reason.BULL_WITHOUT_STRUCTURE)

    def test_opposite_structure_neutralizes_discrete_bias(self):
        snapshot = bullish_snapshot(-1)
        self.assertEqual(snapshot.discrete_bias, 0)
        self.assertEqual(snapshot.alignment, D1Alignment.CONFLICT)
        self.assertEqual(snapshot.reason, D1Reason.BEAR_STRUCTURE_CONFLICTS_BULL_TREND)
        self.assertEqual(
            specific_block_reason(snapshot),
            "d1_bear_structure_conflicts_bull_trend",
        )

    def test_weighted_bias_does_not_override_discrete_conflict(self):
        snapshot = bullish_snapshot(-1)
        self.assertEqual(snapshot.weighted_bias, 0.4)
        self.assertEqual(snapshot.discrete_bias, 0)

    def test_stale_h4_bias_is_detected(self):
        snapshot = bullish_snapshot(-1)
        check = check_bias_synchronization(snapshot, observed_h4_bias=1)
        self.assertTrue(check.stale)
        self.assertEqual(check.expected_bias, 0)
        self.assertEqual(check.observed_bias, 1)

    def test_matching_h4_bias_is_not_stale(self):
        snapshot = bullish_snapshot(-1)
        check = check_bias_synchronization(snapshot, observed_h4_bias=0)
        self.assertFalse(check.stale)


if __name__ == "__main__":
    unittest.main()
