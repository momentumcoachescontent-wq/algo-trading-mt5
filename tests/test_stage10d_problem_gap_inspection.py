from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from python.pipeline.inspect_stage10d_phase2_problem_gaps import inspect_problem_gaps

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "python" / "pipeline" / "inspect_stage10d_phase2_problem_gaps.py"


class Stage10DProblemGapInspectionTests(unittest.TestCase):
    def write_rows(self, path: Path, times: list[datetime]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("time", "open", "high", "low", "close", "tick_volume"),
            )
            writer.writeheader()
            for index, time in enumerate(times):
                writer.writerow(
                    {
                        "time": time.strftime("%Y.%m.%d %H:%M:%S"),
                        "open": 150.0,
                        "high": 150.5,
                        "low": 149.5,
                        "close": 150.2,
                        "tick_volume": 100 + index,
                    }
                )

    def test_only_non_weekend_gaps_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "USDJPY_H4.csv"
            times = [
                datetime(2026, 7, 3, 20),
                datetime(2026, 7, 6, 0),
                datetime(2026, 7, 6, 4),
                datetime(2026, 7, 6, 12),
            ]
            self.write_rows(path, times)

            report = inspect_problem_gaps(
                root,
                symbol="USDJPY",
                timeframes=("H4",),
            )

            dataset = report["datasets"][0]
            self.assertEqual(report["status"], "REVIEW_REQUIRED")
            self.assertEqual(dataset["expected_market_closure_gap_count"], 1)
            self.assertEqual(dataset["problem_gap_count"], 1)
            self.assertEqual(
                dataset["problem_gaps"][0]["previous_time"],
                "2026-07-06 04:00:00",
            )

    def test_complete_sequence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "USDJPY_M15.csv"
            start = datetime(2026, 7, 6, 0)
            self.write_rows(path, [start + timedelta(minutes=15 * index) for index in range(8)])

            report = inspect_problem_gaps(
                root,
                symbol="USDJPY",
                timeframes=("M15",),
            )

            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["problem_gap_count"], 0)

    def test_cli_returns_two_for_review_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "USDJPY_D1.csv"
            self.write_rows(
                path,
                [
                    datetime(2026, 7, 6),
                    datetime(2026, 7, 8),
                ],
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    "--symbol",
                    "USDJPY",
                    "--timeframes",
                    "D1",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("REVIEW_REQUIRED", completed.stdout)
            self.assertIn("problem_gaps=1", completed.stdout)


if __name__ == "__main__":
    unittest.main()
