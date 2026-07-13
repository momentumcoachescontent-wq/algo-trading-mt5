from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python.pipeline.discover_stage10d_phase1_logs import discover_logs
from python.pipeline.validate_stage10d_phase1_shadow import EA_MARKER


class DiscoverStage10DPhase1LogsTests(unittest.TestCase):
    def write_log(self, path: Path, *messages: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"AA 0 00:00:00.000 {EA_MARKER} (USDJPY,H4) {message}" for message in messages]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_selects_init_and_evaluation_files_from_same_log_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "Logs"
            self.write_log(
                logs / "20260710.log",
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
                "[SCOPE_INIT] resolved_mode=SHADOW_ONLY | order_send_allowed=false",
            )
            self.write_log(
                logs / "20260712.log",
                "[D1_CONTEXT_SNAPSHOT] snapshot_match=true | raw_h4_signal=0 | filtered_h4_signal=0",
                "[EDGE_EVAL_WEBHOOK_OK] status=200",
            )

            selected = discover_logs(root)

            self.assertEqual(
                selected,
                (logs / "20260710.log", logs / "20260712.log"),
            )

    def test_prefers_stream_with_evaluation_over_newer_marker_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mql5_logs = root / "MQL5" / "Logs"
            terminal_logs = root / "Logs"
            self.write_log(
                mql5_logs / "20260710.log",
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
                "[D1_CONTEXT_SNAPSHOT] snapshot_match=true | raw_h4_signal=0 | filtered_h4_signal=0",
            )
            self.write_log(
                terminal_logs / "20260713.log",
                "[EA_DEINIT] reason=REASON_CLOSE",
            )

            selected = discover_logs(root)

            self.assertEqual(selected, (mql5_logs / "20260710.log",))

    def test_single_complete_file_is_selected_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "MQL5" / "Logs" / "20260713.log"
            self.write_log(
                log,
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
                "[D1_CONTEXT_SNAPSHOT] snapshot_match=true | raw_h4_signal=0 | filtered_h4_signal=0",
            )

            self.assertEqual(discover_logs(root), (log,))


if __name__ == "__main__":
    unittest.main()
