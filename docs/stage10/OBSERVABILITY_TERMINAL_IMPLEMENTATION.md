# Observability Terminal integration (2026-10-13)

## Scope
- Observational UI only. Does NOT alter MQL5 EA, trade execution, risk policy, decision gates, or existing Cloudflare ingest Worker.
- Branch: feature/observability-terminal-20261013 (based on agent/stage10c-observability-repair).
- React/Vite UI: src/ObservabilityPanel.tsx and ObservabilityPanel.css.
- Dashboard Worker: worker/observability.ts, routed before existing endpoints without changing their responses.
- Supabase: additive public.observability_candles migration, RLS enabled, public/anon/authenticated access revoked.
- Data source: Supabase signal_evals, trades, ea_events; MT5 passive CSV for candles.
- Visual conventions inspired by OpenTerminal, without replacing React/Vite or importing its backend/data providers.
- Warning: graph overlays are reference computations (EMA21 or SMA200) and not necessarily the EA's point-in-time exact values. Candle close time / broker timezone must be validated.

## New routes (GET only)
- /api/observability/assets
- /api/observability/summary?symbol=USDJPY&timeframe=H4&version=v4.44.1
- /api/observability/timeline?symbol=USDJPY&timeframe=H4&limit=300
- /api/observability/candles?symbol=USDJPY&timeframe=H4&limit=1000

Symbol/version/timeframe/limit are validated. Queries are bounded. Scope and data timestamps are returned.
Non-GET methods return HTTP 405. These routes require SUPABASE_SERVICE_ROLE_KEY server-side (never in frontend).
Cloudflare Access or equivalent authentication MUST protect the whole dashboard/API before public exposure;
a service-role secret is NOT an authorization system for end users.

## Importing real candles
1. Obtain an MT5 historical CSV with Date, Time, Open, High, Low, Close and optional TickVol.
2. Record the broker export timezone, including its DST convention. Do not guess UTC.
3. Validate CSV with no database writes:
   python3 python/ops/import_observability_candles.py --csv USDJPY_H4.csv --symbol USDJPY --timeframe H4 --source-timezone UTC
4. When verified, configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY securely in the ingestion environment and rerun with --write.
5. Inspect last_candle and historical price alignment inside the dashboard; when zero bars exist UI shows no-data.

The repository importer is manually invoked and does not provide automatic near-real-time OHLC streaming.
To automate this safely requires a separate MT5-side export schedule; do NOT change the EA to transmit candles.
The empty table is an intentional no-data state, not synthetic pricing.

## Build + tests
cd apps/trading-dashboard
npm ci
npm run build
npm run test:worker
cd ../..
python3 -m unittest tests.test_observability_candle_import -v

GitHub Actions: .github/workflows/observability-terminal-validation.yml

## Cloudflare deployment (not part of GitHub branch commits)
Do not deploy before confirming access restrictions, valid server-side secrets, migrated schema,
MT5 candle source/timezone validation and clean CI. Retain a previous Worker version for rollback.

Staged preview on a machine authenticated to Cloudflare:
cd apps/trading-dashboard
npm ci && npm run build && npm run test:worker
npx wrangler versions upload --config wrangler.jsonc

After verifying the preview and Cloudflare Access, promote that version using your current
approved Wrangler deployment process. Production has not been changed by this branch.

## Operational caveats
- Health from a recent ea_init event does not prove connectivity. Evaluation freshness is separate.
- Performance and blocked reasons come from bounded result sets; do not interpret as full lifetime edge.
- Historical trade entries without a trusted timeframe must not be silently assigned to H4/D1.
- The React chart draws historical candles only when genuinely imported; no prices are synthesized.
- API returns whitelisted signal/trade fields, not raw_payload or account login.
