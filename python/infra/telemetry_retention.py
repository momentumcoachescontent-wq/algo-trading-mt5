"""Bounded, opt-in cleanup of disposable Supabase trading telemetry.

Requires: pip install 'psycopg[binary]'
Set SUPABASE_DB_URL to the Postgres connection string (never commit credentials).
By default this command only reports candidate counts. Use --apply explicitly.
Does NOT touch trades, risk_events, deals, signal_evals, or eval_outcomes.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

# Only disposable, non-trading operational events are cleaned.
# Preserve all signal, order, trade, lifecycle and risk evidence in events.
RETENTION = (
    ("public", "ea_events", "created_at",
     "event = 'ea_init' AND execution_mode = 'DEMO'", 7),
    ("trading_evidence", "events", "received_at",
     "event_type IN ('heartbeat', 'external_account_observation')", 2),
    ("trading_evidence", "batches", "received_at", "TRUE", 2),
)

def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run or prune noncritical MT5 telemetry")
    parser.add_argument("--apply", action="store_true", help="Enable deletions (default dry-run)")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-rows", type=int, default=2000,
                        help="Maximum deletes per table per execution")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000 or not 1 <= args.max_rows <= 20000:
        parser.error("batch-size must be 1..1000, max-rows must be 1..20000")
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        parser.error("SUPABASE_DB_URL is required")
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise SystemExit("Install psycopg: pip install 'psycopg[binary]'") from exc

    with psycopg.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '15s'")
            for schema, table, timestamp, predicate, days in RETENTION:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                relation = sql.Identifier(schema, table)
                column = sql.Identifier(timestamp)
                criteria = sql.SQL(predicate)  # fixed, trusted constants above
                where = sql.SQL("{} < %s AND {}").format(column, criteria)
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {} WHERE {}").format(relation, where),
                    (cutoff,),
                )
                candidates = cur.fetchone()[0]
                print(f"{schema}.{table}: {candidates} candidates (> {days}d)")
                if not args.apply:
                    continue
                remaining = args.max_rows
                removed = 0
                while remaining > 0:
                    n = min(args.batch_size, remaining)
                    # ctid is used only within this single statement; no long-lived IDs.
                    statement = sql.SQL(
                        "WITH victims AS (SELECT ctid FROM {} WHERE {} LIMIT %s "
                        "FOR UPDATE SKIP LOCKED) "
                        "DELETE FROM {} AS target USING victims "
                        "WHERE target.ctid = victims.ctid"
                    ).format(relation, where, relation)
                    cur.execute(statement, (cutoff, n))
                    count = cur.rowcount
                    conn.commit()
                    removed += count
                    remaining -= count
                    if count < n:
                        break
                print(f"  deleted: {removed}; remaining queued: ~{max(0,candidates-removed)}")
    print("Done. VACUUM (ANALYZE) is recommended periodically; it does not shrink files automatically.")

if __name__ == "__main__":
    main()
