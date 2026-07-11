import tempfile
import unittest
from pathlib import Path

from python.pipeline.validate_stage10d_phase1_shadow_strict import (
    strict_lines,
    validate_paths_strict,
)


V4431 = "EMA_MTF_v4431_stage10c_d1_context_integrity (USDJPY,H4)"
V4430 = "EMA_MTF_v4430_stage10c_usdjpy_first_governance_reset (USDJPY,H4)"


def startup_lines() -> list[str]:
    return [
        f"{V4431}\t[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
        f"{V4431}\t[SCOPE_INIT] symbol=USDJPY | resolved_mode=SHADOW_ONLY | order_send_allowed=false",
        f"{V4431}\t[MFE_TRACKER_INIT] symbol=USDJPY | enabled=true | magic=20260711",
        f'{V4431}\t[INIT_V2_LOG] {{"ea_version":"v4.43.1","execution_mode":"SHADOW_ONLY","capital_enabled":false,"order_send_allowed":false}}',
        f"{V4431}\t[F5A4_WEBHOOK_OK] event=ea_init | status=200",
    ]


class StrictShadowValidatorTests(unittest.TestCase):
    def write_log(self, lines: list[str], encoding: str = "utf-8") -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "mixed.log"
        path.write_text("\n".join(lines), encoding=encoding)
        return path

    def test_filters_out_v4430_lines(self):
        path = self.write_log(
            startup_lines()
            + [f"{V4430}\t[TRADE_OPEN_BUY] symbol=USDJPY | ticket=123"]
        )
        selected = strict_lines([path])
        self.assertTrue(selected)
        self.assertTrue(all(V4431 in line for line in selected))
        self.assertFalse(any("TRADE_OPEN_BUY" in line for line in selected))

    def test_real_ea_order_does_not_fail_shadow_startup(self):
        path = self.write_log(
            startup_lines()
            + [f"{V4430}\t[TRADE_OPEN_BUY] symbol=USDJPY | ticket=123"]
        )
        summary = validate_paths_strict([path])
        self.assertEqual(summary.status, "PASS_STARTUP_PENDING_EVALUATION")
        no_order = next(check for check in summary.checks if check.name == "no_order_activity")
        self.assertEqual(no_order.status, "PASS")

    def test_real_ea_webhook_cannot_satisfy_shadow_evaluation_coverage(self):
        lines = startup_lines() + [
            f"{V4431}\t[D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.13 00:00 | "
            "bias_discrete=0 | raw_h4_signal=1 | filtered_h4_signal=0 | "
            "snapshot_match=true | snapshot_id=s1 | h4_consumed_snapshot_id=s1 | "
            "h4_consumed_bias=0",
            f"{V4430}\t[EDGE_EVAL_WEBHOOK_OK] event=edge_eval | status=200",
        ]
        summary = validate_paths_strict([self.write_log(lines)])
        self.assertEqual(summary.status, "FAIL")
        coverage = next(check for check in summary.checks if check.name == "evaluation_webhook")
        self.assertEqual(coverage.status, "FAIL")
        self.assertEqual(summary.edge_webhook_ok, 0)

    def test_valid_shadow_evaluation_passes_with_interleaved_real_ea(self):
        lines = startup_lines() + [
            f"{V4430}\t[TRADE_OPEN_BUY] symbol=USDJPY | ticket=123",
            f"{V4431}\t[D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.13 00:00 | "
            "bias_discrete=0 | raw_h4_signal=1 | filtered_h4_signal=0 | "
            "snapshot_match=true | snapshot_id=s1 | h4_consumed_snapshot_id=s1 | "
            "h4_consumed_bias=0",
            f"{V4430}\t[EDGE_EVAL_WEBHOOK_OK] event=edge_eval | status=200",
            f"{V4431}\t[EDGE_EVAL_WEBHOOK_OK] event=edge_eval | status=200",
        ]
        summary = validate_paths_strict([self.write_log(lines, encoding="utf-16")])
        self.assertEqual(summary.status, "PASS_PHASE1_FORWARD_GATE")
        self.assertEqual(summary.evaluations, 1)
        self.assertEqual(summary.edge_webhook_ok, 1)


if __name__ == "__main__":
    unittest.main()
