import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from python.ops.import_observability_candles import parse_time, read_candles

class ObservabilityCandleImportTest(unittest.TestCase):
    def test_timezone_converted_to_utc(self):
        self.assertEqual(
            parse_time("2026.10.13", "12:00", ZoneInfo("America/Mexico_City")),
            "2026-10-13T18:00:00Z",
        )

    def test_mt5_csv_with_angle_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mt5.csv"
            path.write_text(
                "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\n"
                "2026.10.13\t08:00\t150.10\t150.75\t150.00\t150.60\t200\n"
                "2026.10.13\t12:00\t150.60\t151.00\t150.50\t150.90\t240\n",
                encoding="utf-8",
            )
            rows = read_candles(path, "USDJPY", "H4", ZoneInfo("UTC"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["bar_time"], "2026-10-13T08:00:00Z")
            self.assertEqual(rows[1]["tick_volume"], 240)

    def test_invalid_bar_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text(
                "Date,Time,Open,High,Low,Close\n"
                "2026.10.13,08:00,150,149,148,151\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "CSV line 2"):
                read_candles(path, "USDJPY", "H4", ZoneInfo("UTC"))

if __name__ == "__main__":
    unittest.main()
