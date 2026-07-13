import tempfile
import unittest
from pathlib import Path

from python.pipeline.audit_d1_context_logs import audit_paths


D1_CONFLICT = (
    "[D1_DEBUG] USDJPY | D1=2026.07.08 | structure=-1 | has_structure=true | "
    "ema50=160.29208 | emaPrev=160.21948 | emaRising=true | emaFalling=false | "
    "closeD1=162.07100 | closeH4=162.07100 | d1Above=true | d1Below=false | "
    "h4Above=true | h4Below=false | swingHigh=162.42600 | swingLow=160.48200 | bias=0"
)


class D1AuditTests(unittest.TestCase):
    def write_log(self, content: str, encoding: str = "utf-8") -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "sample.log"
        path.write_text(content, encoding=encoding)
        return path

    def test_classifies_neutral_candidate_as_ungated_not_stale(self):
        content = "\n".join(
            [
                D1_CONFLICT,
                "[ML_VETO_SHADOW] symbol=USDJPY | eval_time=2026.07.08 04:00 | "
                "evaluated=true | direction=buy | target=x",
            ]
        )
        summary = audit_paths([self.write_log(content)])
        self.assertEqual(summary.ungated_candidate_events, 1)
        self.assertEqual(summary.integrity_events, 0)
        self.assertEqual(summary.stale_candidate_events, 1)  # compatibility alias
        self.assertEqual(summary.findings[0].finding_type, "raw_candidate_while_d1_neutral")

    def test_detects_h4_debug_bias_mismatch(self):
        content = "\n".join(
            [
                D1_CONFLICT,
                "[H4_SIGNAL_DEBUG] 2026.07.08 00:00 | USDJPY | bias=+1 | "
                "raw_signal=+0 | signal=+0 | fail=no_ema_touch_bull",
            ]
        )
        summary = audit_paths([self.write_log(content)])
        self.assertEqual(summary.h4_bias_mismatch_events, 1)
        self.assertEqual(summary.integrity_events, 1)

    def test_detects_filtered_signal_during_neutral_context(self):
        content = (
            "[D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.08 04:00 | "
            "bar_h4=2026.07.08 00:00 | bias_discrete=0 | raw_h4_signal=1 | "
            "filtered_h4_signal=1 | snapshot_match=true"
        )
        summary = audit_paths([self.write_log(content)])
        self.assertEqual(summary.snapshot_integrity_events, 1)
        self.assertEqual(summary.integrity_events, 1)

    def test_accepts_raw_candidate_when_filtered_signal_is_zero(self):
        content = (
            "[D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.08 04:00 | "
            "bar_h4=2026.07.08 00:00 | bias_discrete=0 | raw_h4_signal=1 | "
            "filtered_h4_signal=0 | snapshot_match=true"
        )
        summary = audit_paths([self.write_log(content)])
        self.assertEqual(summary.snapshot_integrity_events, 0)

    def test_detects_snapshot_mismatch(self):
        content = (
            "[D1_CONTEXT_SNAPSHOT] symbol=USDJPY | eval_time=2026.07.08 04:00 | "
            "bar_h4=2026.07.08 00:00 | bias_discrete=1 | raw_h4_signal=1 | "
            "filtered_h4_signal=0 | snapshot_match=false"
        )
        summary = audit_paths([self.write_log(content)])
        self.assertEqual(summary.snapshot_integrity_events, 1)

    def test_maps_generic_no_bias_to_specific_context_reason(self):
        content = "\n".join(
            [
                D1_CONFLICT,
                "[DECISION_BLOCKED] symbol=USDJPY | eval_time=2026.07.08 08:00 | "
                "bar_h4=2026.07.08 04:00 | reason=no_bias_context | action_before=BLOCKED |",
            ]
        )
        summary = audit_paths([self.write_log(content)])
        self.assertEqual(summary.generic_no_bias_events, 1)
        finding = summary.findings[0]
        self.assertIn("d1_bear_structure_conflicts_bull_trend", finding.detail)

    def test_reads_utf16_mt5_logs(self):
        content = "\n".join(
            [
                D1_CONFLICT,
                "[ML_VETO_SHADOW] symbol=USDJPY | eval_time=2026.07.08 04:00 | "
                "evaluated=true | direction=buy | target=x",
            ]
        )
        summary = audit_paths([self.write_log(content, encoding="utf-16")])
        self.assertEqual(summary.ungated_candidate_events, 1)


if __name__ == "__main__":
    unittest.main()