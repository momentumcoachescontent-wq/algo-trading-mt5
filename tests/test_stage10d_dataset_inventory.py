from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from python.pipeline.inventory_stage10d_phase2_datasets import build_inventory

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "python" / "pipeline" / "inventory_stage10d_phase2_datasets.py"


class Stage10DDatasetInventoryTests(unittest.TestCase):
    def write_csv(
        self,
        path: Path,
        *,
        start: datetime,
        bars: int,
        step_hours: int = 4,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("time", "open", "high", "low", "close", "tick_volume"),
            )
            writer.writeheader()
            for index in range(bars):
                time = start + timedelta(hours=step_hours * index)
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

    def test_identical_candidates_are_grouped_and_one_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports"
            first = root / "USDJPY_H4.csv"
            second = root / "USDJPY_H4_copy.csv"
            self.write_csv(first, start=datetime(2026, 7, 6), bars=6)
            second.write_bytes(first.read_bytes())

            report = build_inventory((root,), symbol="USDJPY", timeframes=("H4",))
            summary = report["summaries"][0]

            self.assertEqual(report["status"], "PASS")
            self.assertEqual(summary["recommended_action"], "USE_SINGLE_CANDIDATE")
            self.assertEqual(len(summary["duplicate_sha_groups"]), 1)

    def test_split_coverage_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports"
            self.write_csv(
                root / "USDJPY_H4_history.csv",
                start=datetime(2026, 6, 1),
                bars=24,
            )
            self.write_csv(
                root / "USDJPY_H4_recent.csv",
                start=datetime(2026, 7, 1),
                bars=6,
            )

            report = build_inventory((root,), symbol="USDJPY", timeframes=("H4",))
            summary = report["summaries"][0]

            self.assertEqual(report["status"], "REVIEW_REQUIRED")
            self.assertEqual(summary["recommended_action"], "RECONCILE_SPLIT_COVERAGE")
            self.assertIsNone(summary["selected_candidate"])

    def test_cli_runs_directly_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports"
            output = Path(tmp) / "inventory.json"
            self.write_csv(root / "USDJPY_H4.csv", start=datetime(2026, 7, 6), bars=6)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    "--symbol",
                    "USDJPY",
                    "--timeframes",
                    "H4",
                    "--json-out",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.exists())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS")
            self.assertIn("USE_SINGLE_CANDIDATE", completed.stdout)


if __name__ == "__main__":
    unittest.main()
