#!/usr/bin/env python3
"""Passive MT5 CSV -> Supabase observability_candles. Read-only towards trading.

Examples:
python3 python/ops/import_observability_candles.py --csv USDJPY_H4.csv --symbol USDJPY --timeframe H4 --source-timezone UTC
python3 python/ops/import_observability_candles.py --csv USDJPY_H4.csv --symbol USDJPY --timeframe H4 --source-timezone America/New_York --write

Default is dry-run. A timezone must be supplied to avoid silent broker-time drift.
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY only when --write is used.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

def normal(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())

def parse_time(date_value: str, time_value: str, timezone: ZoneInfo) -> str:
    combined = (date_value.strip() + " " + time_value.strip()).strip()
    candidates = [
        "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M", "%Y.%m.%d", "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
    ]
    for layout in candidates:
        try:
            parsed = dt.datetime.strptime(combined, layout)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone)
            return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    raise ValueError("Invalid timestamp: " + repr(combined))

def read_candles(path: Path, symbol: str, timeframe: str, timezone: ZoneInfo) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV requires named columns for Date/Time and OHLC")
        col = {normal(h): h for h in reader.fieldnames}
        def field(row: dict, *names: str, fallback: str = "") -> str:
            for name in names:
                if name in col:
                    return str(row[col[name]] or "").strip()
            return fallback
        expected = ["open", "high", "low", "close"]
        if any(x not in col for x in expected):
            raise ValueError("CSV must contain Open, High, Low and Close columns")
        if not ("date" in col or "datetime" in col or "time" in col):
            raise ValueError("CSV must contain Date, DateTime or Time column")
        rows = {}
        for lineno, row in enumerate(reader, start=2):
            try:
                date = field(row, "datetime", "date", fallback="")
                clock = field(row, "time", fallback="")
                if not date and clock:
                    date, clock = clock, ""
                when = parse_time(date, clock, timezone)
                o, h, l, c = (float(field(row, x)) for x in expected)
                if not (h >= max(o, c) > 0 and 0 < l <= min(o, c) and h >= l):
                    raise ValueError("Invalid OHLC ordering or price")
                volume = field(row, "tickvolume", "tickvol", "volume", "vol")
                candle = {
                    "symbol": symbol, "timeframe": timeframe, "bar_time": when,
                    "open": o, "high": h, "low": l, "close": c,
                    "tick_volume": int(float(volume)) if volume else None,
                    "source": "MT5_EXPORT",
                }
                if candle["tick_volume"] is not None and candle["tick_volume"] < 0:
                    raise ValueError("Negative volume")
                rows[when] = candle
            except Exception as exc:
                raise ValueError("CSV line " + str(lineno) + ": " + str(exc)) from exc
    return [rows[k] for k in sorted(rows)]

def upload(rows: list[dict], url: str, key: str) -> None:
    endpoint = url.rstrip("/") + "/rest/v1/observability_candles?on_conflict=symbol,timeframe,bar_time"
    for start in range(0, len(rows), 250):
        chunk = rows[start:start + 250]
        request = urllib.request.Request(
            endpoint, data=json.dumps(chunk).encode("utf-8"), method="POST",
            headers={
                "apikey": key, "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError("Unexpected HTTP status: " + str(response.status))
        except urllib.error.HTTPError as exc:
            raise RuntimeError("Supabase import failed: HTTP " + str(exc.code)) from exc
        print("Uploaded", min(start + len(chunk), len(rows)), "of", len(rows), "bars")

def main() -> int:
    parser = argparse.ArgumentParser(description="Passive MT5 OHLC importer")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--symbol", type=str, required=True)
    parser.add_argument("--timeframe", choices=("H4", "D1"), required=True)
    parser.add_argument("--source-timezone", type=str, required=True,
                        help="IANA time zone of exported MT5 broker timestamps, e.g. UTC")
    parser.add_argument("--write", action="store_true", help="Perform upsert (otherwise dry-run)")
    args = parser.parse_args()
    symbol = args.symbol.upper()
    if not re.fullmatch(r"[A-Z0-9._-]{2,24}", symbol):
        parser.error("Invalid MT5 symbol")
    try:
        tz = ZoneInfo(args.source_timezone)
        rows = read_candles(args.csv, symbol, args.timeframe, tz)
    except (OSError, KeyError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    print("Candles:", len(rows), "symbol:", symbol, "tf:", args.timeframe,
          "UTC range:", rows[0]["bar_time"] if rows else "-", "to", rows[-1]["bar_time"] if rows else "-")
    if not args.write:
        print("DRY RUN — no database changes. Pass --write to import.")
        return 0
    if not rows:
        print("No data to upload")
        return 1
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key or not url.startswith("https://"):
        print("ERROR: secure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required", file=sys.stderr)
        return 1
    try:
        upload(rows, url, key)
    except (RuntimeError, urllib.error.URLError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
