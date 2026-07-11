import unittest

from python.pipeline.validate_stage10d_phase1_shadow import validate_lines


PREFIX = "EMA_MTF_v4431_stage10c_d1_context_integrity (USDJPY,H4)"


def base_session(magic=20260711):
    return [
        f"{PREFIX} [ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
        f"{PREFIX} [SCOPE_INIT] symbol=USDJPY | requested_mode=SHADOW_ONLY | resolved_mode=SHADOW_ONLY | order_send_allowed=false",
        f"{PREFIX} [MFE_TRACKER_INIT] symbol=USDJPY | enabled=true | magic={magic}",
        f'{PREFIX} [INIT_V2_LOG] {{"ea_version":"v4.43.1","execution_mode":"SHADOW_ONLY","execution_scope":{{"capital_enabled":false,"order_send_allowed":false}}}}',
        f"{PREFIX} [F5A4_WEBHOOK_OK] event=ea_init | status=200",
    ]


class ShadowValidatorTests(unittest.TestCase):
    def test_startup_passes_pending_evaluation(self):
        summary = validate_lines(base_session())
        self.assertEqual(summary.status, "PASS_STARTUP_PENDING_EVALUATION")
        self.assertEqual(summary.observed_magic, 20260711)

    def test_neutral_raw_candidate_filtered_zero_passes(self):
        lines = base_session() + [
            f"{PREFIX} [D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.08 04:00 | bias_discrete=0 | snapshot_id=a | h4_consumed_snapshot_id=a | h4_consumed_bias=0 | raw_h4_signal=1 | filtered_h4_signal=0 | snapshot_match=true",
            f"{PREFIX} [EDGE_EVAL_WEBHOOK_OK] status=200",
        ]
        summary = validate_lines(lines)
        self.assertEqual(summary.status, "PASS_PHASE1_FORWARD_GATE")
        self.assertTrue(summary.evaluation_results[0].passed)

    def test_neutral_promoted_candidate_fails(self):
        lines = base_session() + [
            f"{PREFIX} [D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.08 04:00 | bias_discrete=0 | snapshot_id=a | h4_consumed_snapshot_id=a | h4_consumed_bias=0 | raw_h4_signal=1 | filtered_h4_signal=1 | snapshot_match=true",
            f"{PREFIX} [EDGE_EVAL_WEBHOOK_OK] status=200",
        ]
        summary = validate_lines(lines)
        self.assertEqual(summary.status, "FAIL")
        self.assertIn("neutral_bias_promoted_signal", summary.evaluation_results[0].violations)

    def test_snapshot_mismatch_fails(self):
        lines = base_session() + [
            f"{PREFIX} [D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.08 04:00 | bias_discrete=1 | snapshot_id=a | h4_consumed_snapshot_id=b | h4_consumed_bias=1 | raw_h4_signal=1 | filtered_h4_signal=0 | snapshot_match=false",
        ]
        summary = validate_lines(lines)
        self.assertEqual(summary.status, "FAIL")

    def test_wrong_magic_fails(self):
        summary = validate_lines(base_session(magic=20260527))
        self.assertEqual(summary.status, "FAIL")


if __name__ == "__main__":
    unittest.main()
