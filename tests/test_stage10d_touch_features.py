from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from python.research.stage10d_data_readiness import sha256_file
from python.research.stage10d_touch_features import (
    TouchThresholds,
    _classify_gap,
    _touch_side,
    build_touch_artifact,
    build_touch_features,
    write_touch_artifact,
)


class Stage10DTouchFeatureTests(unittest.TestCase):
    def thresholds(self) -> TouchThresholds:
        return TouchThresholds(exact_atr=0.25, soft_atr=0.50, extended_atr=1.50)

    def rows(self, count: int = 30, *, start: datetime | None = None):
        start = start or datetime(2026, 1, 5, 0, 0)
        values = []
        for index in range(count):
            close = 100.0 + index * 0.01
            values.append(
                {
                    "time": start + timedelta(hours=4 * index),
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 100.0,
                    "symbol": "USDJPY",
                    "timeframe": "H4",
                }
            )
        return values

    def test_buy_wrong_side_is_null_not_zero(self):
        result = _touch_side(
            direction="BUY",
            high=99.0,
            low=98.0,
            ema=100.0,
            atr=2.0,
            indicators_valid=True,
            thresholds=self.thresholds(),
        )
        self.assertIsNone(result["touch_gap_buy_price"])
        self.assertIsNone(result["touch_gap_buy_atr"])
        self.assertEqual(result["touch_class_buy"], "unknown")
        self.assertIsNone(result["geometric_contact_buy"])

    def test_sell_wrong_side_is_null_not_zero(self):
        result = _touch_side(
            direction="SELL",
            high=102.0,
            low=101.0,
            ema=100.0,
            atr=2.0,
            indicators_valid=True,
            thresholds=self.thresholds(),
        )
        self.assertIsNone(result["touch_gap_sell_price"])
        self.assertIsNone(result["touch_gap_sell_atr"])
        self.assertEqual(result["touch_class_sell"], "unknown")

    def test_geometric_contact_and_threshold_bands(self):
        buy = _touch_side(
            direction="BUY",
            high=101.0,
            low=99.0,
            ema=100.0,
            atr=2.0,
            indicators_valid=True,
            thresholds=self.thresholds(),
        )
        self.assertEqual(buy["touch_gap_buy_price"], 0.0)
        self.assertEqual(buy["touch_gap_buy_atr"], 0.0)
        self.assertTrue(buy["geometric_contact_buy"])
        self.assertTrue(buy["touch_zone_exact_buy"])
        self.assertEqual(buy["touch_class_buy"], "inside_exact")

        self.assertEqual(_classify_gap(0.25, self.thresholds()), "inside_exact")
        self.assertEqual(_classify_gap(0.30, self.thresholds()), "outside_exact_inside_soft")
        self.assertEqual(_classify_gap(1.00, self.thresholds()), "outside_soft_inside_extended")
        self.assertEqual(_classify_gap(1.51, self.thresholds()), "outside_extended")

    def test_future_rows_do_not_change_past_features(self):
        base_rows = self.rows(12)
        base = build_touch_features(
            base_rows,
            ema_period=3,
            atr_period=2,
            thresholds=self.thresholds(),
        )
        future_row = dict(self.rows(13)[-1])
        future_row.update({"open": 150.0, "high": 170.0, "low": 130.0, "close": 160.0})
        extended = build_touch_features(
            [*base_rows, future_row],
            ema_period=3,
            atr_period=2,
            thresholds=self.thresholds(),
        )
        for left, right in zip(base, extended[: len(base)]):
            self.assertEqual(left, right)

    def test_governed_gap_resets_indicators_and_requires_warmup(self):
        start = datetime(2026, 1, 5, 0, 0)
        rows = self.rows(3, start=start)
        rows.extend(self.rows(4, start=start + timedelta(hours=20)))
        features = build_touch_features(
            rows,
            excluded_bar_times=(
                "2026-01-05 12:00:00",
                "2026-01-05 16:00:00",
            ),
            ema_period=3,
            atr_period=2,
            thresholds=self.thresholds(),
        )
        first_after_gap = next(row for row in features if row["time"] == start + timedelta(hours=20))
        self.assertEqual(first_after_gap["segment_reset_reason"], "governed_data_gap")
        self.assertFalse(first_after_gap["touch_feature_eligible"])
        self.assertEqual(first_after_gap["touch_feature_eligibility_reason"], "ema_warmup")

        third_after_gap = next(row for row in features if row["time"] == start + timedelta(hours=28))
        self.assertTrue(third_after_gap["touch_feature_eligible"])
        self.assertEqual(third_after_gap["segment_id"], 1)

    def _write_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("TIME", "OPEN", "HIGH", "LOW", "CLOSE", "TICK_VOLUME"),
            )
            writer.writeheader()
            for row in self.rows(30):
                writer.writerow(
                    {
                        "TIME": row["time"].strftime("%Y-%m-%d %H:%M:%S"),
                        "OPEN": row["open"],
                        "HIGH": row["high"],
                        "LOW": row["low"],
                        "CLOSE": row["close"],
                        "TICK_VOLUME": row["volume"],
                    }
                )

    def _write_manifest(self, path: Path, csv_path: Path, *, source_hash: str | None = None) -> None:
        payload = {
            "governed_manifest_id": "governed-test-id",
            "research_eligible": True,
            "source_sha256": source_hash or sha256_file(csv_path),
            "symbol": "USDJPY",
            "timeframe": "H4",
            "excluded_bar_times": [],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_artifact_identity_is_deterministic_and_writer_emits_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "USDJPY_H4.csv"
            manifest_path = root / "governed_manifest.json"
            self._write_csv(csv_path)
            self._write_manifest(manifest_path, csv_path)

            first, first_features = build_touch_artifact(csv_path, manifest_path)
            second, _ = build_touch_artifact(csv_path, manifest_path)
            self.assertEqual(first.feature_artifact_id, second.feature_artifact_id)
            self.assertGreater(first.eligible_row_count, 0)
            outputs = write_touch_artifact(first, first_features, root / "out")
            self.assertTrue(outputs["touch_manifest"].exists())
            self.assertTrue(outputs["touch_features"].exists())

    def test_checksum_mismatch_blocks_feature_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "USDJPY_H4.csv"
            manifest_path = root / "governed_manifest.json"
            self._write_csv(csv_path)
            self._write_manifest(manifest_path, csv_path, source_hash="0" * 64)
            with self.assertRaisesRegex(ValueError, "checksum"):
                build_touch_artifact(csv_path, manifest_path)


if __name__ == "__main__":
    unittest.main()
