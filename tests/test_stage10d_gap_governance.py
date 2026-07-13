from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from python.research.stage10d_gap_governance import evaluate_gap_governance


class Stage10DGapGovernanceTests(unittest.TestCase):
    def rows(self, *, missing: set[datetime] | None = None, duplicate: bool = False):
        missing = missing or set()
        start = datetime(2026, 7, 6, 0, 0)
        values = []
        for index in range(8):
            time = start + timedelta(hours=4 * index)
            if time in missing:
                continue
            values.append(
                {
                    "time": time,
                    "open": 150.0,
                    "high": 150.5,
                    "low": 149.5,
                    "close": 150.2,
                    "volume": 100.0,
                }
            )
        if duplicate:
            values.append(dict(values[-1]))
        return values

    def policy(self, classification: str, previous: str, current: str):
        return {
            "symbol": "USDJPY",
            "rules": [
                {
                    "rule_id": "test-rule",
                    "timeframe": "H4",
                    "previous_time": previous,
                    "current_time": current,
                    "classification": classification,
                    "action": "EXCLUDE_WINDOWS_CROSSING_GAP",
                    "rationale": "test",
                }
            ],
        }

    def test_governed_gap_passes_with_exclusions(self):
        missing = {datetime(2026, 7, 6, 8, 0)}
        report = evaluate_gap_governance(
            self.rows(missing=missing),
            symbol="USDJPY",
            timeframe="H4",
            policy=self.policy(
                "GOVERNED_DATA_GAP",
                "2026-07-06 04:00:00",
                "2026-07-06 12:00:00",
            ),
        )
        self.assertEqual(report.status, "PASS_WITH_GOVERNED_EXCLUSIONS")
        self.assertEqual(report.governed_gap_count, 1)
        self.assertEqual(report.governed_gaps[0].missing_bar_times, ("2026-07-06 08:00:00",))

    def test_pending_calendar_blocks_final_manifest(self):
        missing = {datetime(2026, 7, 6, 8, 0)}
        report = evaluate_gap_governance(
            self.rows(missing=missing),
            symbol="USDJPY",
            timeframe="H4",
            policy=self.policy(
                "PENDING_BROKER_CALENDAR_CONFIRMATION",
                "2026-07-06 04:00:00",
                "2026-07-06 12:00:00",
            ),
        )
        self.assertEqual(report.status, "PENDING_BROKER_CALENDAR")
        self.assertEqual(report.pending_calendar_gap_count, 1)

    def test_unmatched_gap_fails(self):
        missing = {datetime(2026, 7, 6, 8, 0)}
        report = evaluate_gap_governance(
            self.rows(missing=missing),
            symbol="USDJPY",
            timeframe="H4",
            policy={"symbol": "USDJPY", "rules": []},
        )
        self.assertEqual(report.status, "FAIL_UNGOVERNED_GAPS")
        self.assertEqual(report.unmatched_gap_count, 1)

    def test_structural_violation_has_priority(self):
        report = evaluate_gap_governance(
            self.rows(duplicate=True),
            symbol="USDJPY",
            timeframe="H4",
            policy={"symbol": "USDJPY", "rules": []},
        )
        self.assertEqual(report.status, "FAIL_STRUCTURAL")
        self.assertGreater(report.structural_violation_count, 0)


if __name__ == "__main__":
    unittest.main()
