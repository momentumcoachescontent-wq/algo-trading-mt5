from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python.pipeline.diagnose_stage10d_phase2_inventory import render_diagnostics


class Stage10DInventoryDiagnosticsTests(unittest.TestCase):
    def test_renders_quality_failure_counts(self) -> None:
        report = {
            "status": "FAIL",
            "symbol": "USDJPY",
            "candidates": [
                {
                    "path": "/tmp/USDJPY_H4.csv",
                    "timeframe": "H4",
                    "parse_status": "PASS",
                    "parse_error": None,
                    "quality_status": "FAIL",
                    "row_count": 100,
                    "first_bar_time": "2026-01-01 00:00:00",
                    "last_bar_time": "2026-01-20 12:00:00",
                    "duplicate_count": 1,
                    "source_order_violation_count": 2,
                    "ohlc_violation_count": 3,
                    "nonpositive_volume_count": 4,
                    "missing_export_segment_gap_count": 5,
                    "unknown_gap_count": 6,
                    "source_sha256": "abc123",
                }
            ],
        }

        rendered = render_diagnostics(report)

        self.assertIn("quality      : FAIL", rendered)
        self.assertIn("duplicates=1 order=2 ohlc=3 volume=4", rendered)
        self.assertIn("missing_export_segment=5 unknown=6", rendered)
        self.assertIn("sha256       : abc123", rendered)

    def test_renders_parse_error(self) -> None:
        report = {
            "status": "FAIL",
            "symbol": "USDJPY",
            "candidates": [
                {
                    "path": "/tmp/USDJPY_D1.csv",
                    "timeframe": "D1",
                    "parse_status": "FAIL",
                    "parse_error": "Missing required columns: close",
                }
            ],
        }

        rendered = render_diagnostics(report)

        self.assertIn("parse_status : FAIL", rendered)
        self.assertIn("Missing required columns: close", rendered)


if __name__ == "__main__":
    unittest.main()
