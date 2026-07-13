from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from python.pipeline.inspect_stage10d_phase2_gap_sources import inspect_gap_sources


class Stage10DGapSourceInspectionTests(unittest.TestCase):
    def write_csv(
        self,
        path: Path,
        *,
        start: datetime,
        bars: int,
        step_hours: int = 4,
        skip: set[datetime] | None = None,
        price_shift: float = 0.0,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        skip = skip or set()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("time", "open", "high", "low", "close", "tick_volume"),
            )
            writer.writeheader()
            for index in range(bars):
                timestamp = start + timedelta(hours=step_hours * index)
                if timestamp in skip:
                    continue
                base = 150.0 + price_shift
                writer.writerow(
                    {
                        "time": timestamp.strftime("%Y.%m.%d %H:%M:%S"),
                        "open": base,
                        "high": base + 0.5,
                        "low": base - 0.5,
                        "close": base + 0.2,
                        "tick_volume": 100 + index,
                    }
                )

    def test_complete_consistent_repair_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exports = root / "exports"
            archive = root / "data" / "raw" / "mt5_exports"
            start = datetime(2024, 7, 2, 12)
            missing = {datetime(2024, 7, 2, 16), datetime(2024, 7, 2, 20)}
            primary = exports / "USDJPY_H4.csv"
            self.write_csv(primary, start=start, bars=4, skip=missing)
            self.write_csv(archive / "USDJPY_H4.csv", start=start, bars=4)

            report = inspect_gap_sources(
                primary,
                (root,),
                symbol="USDJPY",
                timeframe="H4",
                gaps=((start, datetime(2024, 7, 3, 0)),),
            )

            self.assertEqual(report["status"], "COMPLETE_CONSISTENT_REPAIR_EVIDENCE")
            self.assertEqual(report["gaps"][0]["missing_bars"], 2)
            self.assertTrue(
                all(
                    bar["status"] == "CONSISTENT_SOURCE_VALUE"
                    for bar in report["gaps"][0]["bars"]
                )
            )

    def test_partial_repair_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exports = root / "exports"
            archive = root / "data" / "raw" / "mt5_exports"
            start = datetime(2024, 7, 2, 12)
            missing = {datetime(2024, 7, 2, 16), datetime(2024, 7, 2, 20)}
            primary = exports / "USDJPY_H4.csv"
            self.write_csv(primary, start=start, bars=4, skip=missing)
            self.write_csv(
                archive / "USDJPY_H4.csv",
                start=start,
                bars=4,
                skip={datetime(2024, 7, 2, 20)},
            )

            report = inspect_gap_sources(
                primary,
                (root,),
                symbol="USDJPY",
                timeframe="H4",
                gaps=((start, datetime(2024, 7, 3, 0)),),
            )

            self.assertEqual(report["status"], "PARTIAL_REPAIR_EVIDENCE")

    def test_conflicting_repair_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exports = root / "exports"
            archive = root / "data" / "raw" / "mt5_exports"
            prepared = root / "data" / "raw" / "prepared"
            start = datetime(2024, 7, 2, 12)
            missing = {datetime(2024, 7, 2, 16), datetime(2024, 7, 2, 20)}
            primary = exports / "USDJPY_H4.csv"
            self.write_csv(primary, start=start, bars=4, skip=missing)
            self.write_csv(archive / "USDJPY_H4.csv", start=start, bars=4)
            self.write_csv(
                prepared / "USDJPY_H4.csv",
                start=start,
                bars=4,
                price_shift=1.0,
            )

            report = inspect_gap_sources(
                primary,
                (root,),
                symbol="USDJPY",
                timeframe="H4",
                gaps=((start, datetime(2024, 7, 3, 0)),),
            )

            self.assertEqual(report["status"], "CONFLICTING_REPAIR_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
