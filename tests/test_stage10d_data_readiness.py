from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from python.research.stage10d_data_readiness import (
    build_readiness_bundle,
    load_mt5_csv,
    write_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "python" / "pipeline" / "stage10d_phase2_data_readiness.py"


class Stage10DDataReadinessTests(unittest.TestCase):
    def write_csv(self, path: Path, rows: list[dict[str, object]], delimiter: str = ",") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("time", "open", "high", "low", "close", "tick_volume"),
                delimiter=delimiter,
            )
            writer.writeheader()
            writer.writerows(rows)

    def build(self, path: Path, timeframe: str = "H4"):
        return build_readiness_bundle(
            path,
            symbol="USDJPY",
            timeframe=timeframe,
            broker="test-broker",
            terminal="test-terminal",
            server_timezone="broker-server-time",
            export_timestamp_utc="2026-07-13T03:00:00Z",
        )

    def test_complete_h4_with_weekend_closure_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usd_jpy_h4.csv"
            self.write_csv(
                path,
                [
                    {"time": "2026.07.10 16:00:00", "open": 146.0, "high": 146.4, "low": 145.8, "close": 146.2, "tick_volume": 100},
                    {"time": "2026.07.10 20:00:00", "open": 146.2, "high": 146.5, "low": 146.0, "close": 146.3, "tick_volume": 110},
                    {"time": "2026.07.13 00:00:00", "open": 146.3, "high": 146.6, "low": 146.1, "close": 146.4, "tick_volume": 120},
                ],
            )

            bundle = self.build(path)

            self.assertEqual(bundle.quality.status, "PASS")
            self.assertEqual(bundle.quality.expected_market_closure_gap_count, 1)
            self.assertEqual(bundle.quality.missing_export_segment_gap_count, 0)
            self.assertEqual(bundle.quality.source_order_violation_count, 0)
            self.assertFalse(bundle.manifest.synthetic)

    def test_weekday_missing_bar_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usd_jpy_h4.csv"
            self.write_csv(
                path,
                [
                    {"time": "2026.07.13 00:00:00", "open": 146.0, "high": 146.4, "low": 145.8, "close": 146.2, "tick_volume": 100},
                    {"time": "2026.07.13 08:00:00", "open": 146.2, "high": 146.5, "low": 146.0, "close": 146.3, "tick_volume": 110},
                ],
            )

            bundle = self.build(path)

            self.assertEqual(bundle.quality.status, "FAIL")
            self.assertEqual(bundle.quality.missing_export_segment_gap_count, 1)
            self.assertEqual(bundle.quality.gaps[0].missing_bars, 1)

    def test_duplicate_and_ohlc_violation_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usd_jpy_h4.csv"
            self.write_csv(
                path,
                [
                    {"time": "2026.07.13 00:00:00", "open": 146.0, "high": 145.9, "low": 145.8, "close": 146.2, "tick_volume": 100},
                    {"time": "2026.07.13 00:00:00", "open": 146.0, "high": 146.4, "low": 145.8, "close": 146.2, "tick_volume": 100},
                ],
            )

            bundle = self.build(path)

            self.assertEqual(bundle.quality.status, "FAIL")
            self.assertEqual(bundle.quality.duplicate_count, 1)
            self.assertEqual(bundle.quality.ohlc_violation_count, 1)

    def test_out_of_order_source_rows_fail_even_when_coverage_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usd_jpy_h4.csv"
            self.write_csv(
                path,
                [
                    {"time": "2026.07.13 04:00:00", "open": 146.2, "high": 146.5, "low": 146.0, "close": 146.3, "tick_volume": 110},
                    {"time": "2026.07.13 00:00:00", "open": 146.0, "high": 146.4, "low": 145.8, "close": 146.2, "tick_volume": 100},
                ],
            )

            bundle = self.build(path)

            self.assertEqual(bundle.quality.status, "FAIL")
            self.assertEqual(bundle.quality.source_order_violation_count, 1)
            self.assertEqual(bundle.quality.missing_export_segment_gap_count, 0)

    def test_tab_delimited_split_date_time_mt5_export_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usd_jpy_h4.tsv"
            path.write_text(
                "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICK_VOLUME>\n"
                "2026.07.13\t00:00:00\t146.0\t146.4\t145.8\t146.2\t100\n",
                encoding="utf-8",
            )

            rows = load_mt5_csv(path, symbol="USDJPY", timeframe="H4")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["symbol"], "USDJPY")
            self.assertEqual(rows[0]["time"].strftime("%Y-%m-%d %H:%M:%S"), "2026-07-13 00:00:00")

    def test_manifest_id_is_stable_and_outputs_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "usd_jpy_h4.csv"
            self.write_csv(
                path,
                [
                    {"time": "2026.07.13 00:00:00", "open": 146.0, "high": 146.4, "low": 145.8, "close": 146.2, "tick_volume": 100},
                    {"time": "2026.07.13 04:00:00", "open": 146.2, "high": 146.5, "low": 146.0, "close": 146.3, "tick_volume": 110},
                ],
            )

            first = self.build(path)
            second = self.build(path)
            outputs = write_bundle(first, root / "out")

            self.assertEqual(first.manifest.data_manifest_id, second.manifest.data_manifest_id)
            self.assertTrue(all(output.exists() for output in outputs.values()))
            manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["quality_status"], "PASS")
            self.assertEqual(manifest["server_timezone"], "broker-server-time")
            self.assertEqual(manifest["source_order_violation_count"], 0)

    def test_cli_returns_two_when_quality_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "usd_jpy_h4.csv"
            self.write_csv(
                path,
                [
                    {"time": "2026.07.13 00:00:00", "open": 146.0, "high": 146.4, "low": 145.8, "close": 146.2, "tick_volume": 100},
                    {"time": "2026.07.13 08:00:00", "open": 146.2, "high": 146.5, "low": 146.0, "close": 146.3, "tick_volume": 110},
                ],
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    str(path),
                    "--symbol", "USDJPY",
                    "--timeframe", "H4",
                    "--broker", "test-broker",
                    "--terminal", "test-terminal",
                    "--server-timezone", "broker-server-time",
                    "--output-dir", str(root / "out"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
