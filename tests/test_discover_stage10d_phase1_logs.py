from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from python.pipeline.discover_stage10d_phase1_logs import discover_logs
from python.pipeline.validate_stage10d_phase1_shadow import EA_MARKER

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_SCRIPT = ROOT / "python" / "pipeline" / "discover_stage10d_phase1_logs.py"


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

    def test_latest_init_supersedes_older_completed_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "Logs"
            self.write_log(
                logs / "20260710.log",
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
            )
            self.write_log(
                logs / "20260711.log",
                "[D1_CONTEXT_SNAPSHOT] snapshot_match=true | raw_h4_signal=0 | filtered_h4_signal=0",
                "[EDGE_EVAL_WEBHOOK_OK] status=200",
            )
            self.write_log(
                logs / "20260712.log",
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
                "[SCOPE_INIT] resolved_mode=SHADOW_ONLY | order_send_allowed=false",
            )

            selected = discover_logs(root)

            self.assertEqual(selected, (logs / "20260712.log",))

    def test_latest_init_stream_wins_even_when_older_stream_has_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mql5_logs = root / "MQL5" / "Logs"
            terminal_logs = root / "Logs"
            self.write_log(
                mql5_logs / "20260711.log",
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
                "[D1_CONTEXT_SNAPSHOT] snapshot_match=true | raw_h4_signal=0 | filtered_h4_signal=0",
            )
            self.write_log(
                terminal_logs / "20260712.log",
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
            )

            selected = discover_logs(root)

            self.assertEqual(selected, (terminal_logs / "20260712.log",))

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

    def test_direct_cli_bootstraps_repository_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "Logs" / "20260713.log"
            self.write_log(
                log,
                "[ENTRY_STATE_RESET] symbol=USDJPY | reason=on_init | previous_action=NONE",
                "[D1_CONTEXT_SNAPSHOT] snapshot_match=true | raw_h4_signal=0 | filtered_h4_signal=0",
            )

            completed = subprocess.run(
                [sys.executable, str(DISCOVERY_SCRIPT), str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), str(log))
            self.assertNotIn("ModuleNotFoundError", completed.stderr)


if __name__ == "__main__":
    unittest.main()
