# MT5 telemetry quota control (pilot, 2026-11-15)

## Root cause and objective
Supabase `algo-trading` grew to ~5.9 GB, driven mainly by `ea_events`
`ea_init` messages (roughly 69k for USDJPY v5.2.0), some containing
~200 kB of historical snapshots. Database storage was subsequently reduced
to ~104 MB manually. Organization-level Storage quota is a **separate**
issue: `youtube_content_os/social-videos` still holds ~3 GB and HTTP 402
cannot be fixed by trading telemetry changes.

## Changes in this branch
- Webhook: for an init with `boot_id`, check for an existing row with the same
  `boot_id`, `symbol`, `ea_version` and `ea_init` before persisting.
  This is best-effort deduplication, **not** an atomic unique constraint.
- Lifecycle payload: persist a small metadata summary instead of copying
  positions, trades, chart history, analysis_events, and equity arrays into
  each `ea_init`/`ea_deinit` JSON payload. Trade events and signal evaluation
  handlers are not altered. Critical execution_scope still persists in its own
  column.
- Dashboard: smaller per-query limits and reduced data-quality sample output.
- Python maintenance: opt-in, batched retention of DEMO `ea_init` (7 days),
  heartbeats and external observations (2 days), and raw evidence batches (2 days).
  It leaves trades, risk_events, deals, signals and outcomes untouched.

## Review and rollout
**Do not deploy straight to live trading without tests.** The actual v5.2.0 MQL5
Expert source is not present on main at the time of this patch. Sync it from
the terminal with the version that is actually running. Then ensure OnInit
emits once per boot; OnTick/OnTimer must never call `ea_init`. Add an
incremental telemetry event if needed, rather than transmitting all chart
history.

Check the Worker against a DEMO account using these scenarios:
1. New `ea_init` persists one bounded row.
2. Repeated `ea_init` with same boot_id does not create a row.
3. Next real boot_id produces a new record.
4. A `trade_open`/`trade_close` is not affected.
5. When Supabase responds HTTP 402, the Worker reports failure and does not
   silently treat an unsuccessful write as success.
6. Check Cloudflare rate and latency; the dedup GET still creates API traffic.

Local validation:
```bash
cd infra/worker
npm ci
npm test
npm run typecheck
```

## Local Python cleanup
No cleanup runs automatically on merge.
Use the **pooled or direct Postgres** connection string for the correct
`algo-trading` project, stored only in a local environment variable:
```bash
python3 -m pip install 'psycopg[binary]'
export SUPABASE_DB_URL='postgresql://...'
python3 python/infra/telemetry_retention.py
python3 python/infra/telemetry_retention.py --apply --batch-size 500 --max-rows 2000
```
The first command is read-only. Only run --apply after checking the dry run,
backups, and that downstream pipelines do not need old evidence batches.
Run the job at most daily during the DEMO pilot; monitor counts, table sizes
and retention after each run. Never run `DELETE FROM storage.objects` for
videos; Supabase Storage requires the Storage API.

## Monitoring SQL
```sql
select event,ea_version,count(*) n,
       pg_size_pretty(sum(pg_column_size(raw_payload))::bigint) payload
from public.ea_events
group by 1,2 order by n desc;

select relname,pg_size_pretty(pg_total_relation_size(relid)) total,
       n_live_tup,n_dead_tup
from pg_stat_user_tables
where schemaname in ('public','trading_evidence')
order by pg_total_relation_size(relid) desc;
```

## Operational guardrails
- Avoid historical deletion of real trade, signal, or risk evidence.
- Keep DB retention and video Storage cleanup as separate workflows.
- Stop the pilot if telemetry ingestion generates excessive 402/429 responses.
- The dashboard and Python cleanup patches need to be synced to the Mac and
  tested before any production deployment.
