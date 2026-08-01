# Stage10C Lifecycle Observability — Operational Closure

## Decision

```text
status = CLOSED / PASS
worker_build = 3.3.1-stage10c-lifecycle-observability
deployment_version_id = 798bb41f-cc53-46da-9b21-b67f3f74a2d7
strategy_change = none
supabase_schema_change = none
capital_scope_change = none
```

The lifecycle observability repair is approved for production. The organic
`ea_init` path passed end to end for both active USDJPY H4 EAs after the Worker
deployment.

## End-to-end evidence

| EA | Execution contract | Request ID | Persistence | Contract gate |
|---|---|---|---|---|
| `v4.43.0` | `REAL` | `0c32e2ae` | `PASS_PERSISTENCE` | `PASS_V4430_REAL` |
| `v4.43.1` | `SHADOW_ONLY` | `7cd61b2e` | `PASS_PERSISTENCE` | `PASS_V4431_SHADOW_ONLY` |

Both rows were persisted on 2026-08-01 after deployment. For each row:

- `request_id` matched `raw_payload.worker_request_id`;
- `rows_per_request = 1`;
- `guard_version` matched the payload;
- `boot_id` and `terminal_time` were present;
- execution mode, capital permission and order permission remained isolated.

The Worker validation evidence was:

```text
typecheck = PASS
tests = 22/22 PASS
production vulnerabilities = 0
deployment traffic = 100%
health = ok
```

## `ea_deinit` disposition

`ea_deinit` is best-effort lifecycle telemetry and is not a capital, order,
trade-linking or signal-decision control.

Observed behavior distinguishes two deinitialization paths:

1. With the terminal still operational (`REASON_REMOVE`), `OnDeinit` executed
   the synchronous HTTP request and received a real Worker response. Historical
   evidence includes HTTP `401` when the local secret was intentionally absent,
   proving that the request reached the Worker.
2. During terminal shutdown (`REASON_CLOSE`), both active EAs built and printed
   complete `DEINIT_V2_LOG` payloads, but the synchronous request failed locally
   and immediately with `last_error=4006`. No request reached the Worker.

MQL5 defines error `4006` as an invalid or damaged dynamic array. It also
defines `REASON_CLOSE=9` as terminal shutdown. Because `WebRequest` normally
returns an HTTP response code or `-1`, the observed `status=1003` is not treated
as an HTTP response and must not be interpreted as a Worker or Supabase error.

### Classification

```text
REASON_CLOSE ea_deinit delivery = KNOWN_PLATFORM_TEARDOWN_LIMITATION
severity = non-blocking
retry guarantee = none
local payload evidence = retained in MT5 log
continuity recovery = next ea_init boot_id
```

No EA recompilation is authorized for this closure. Changing both active EAs
only to attempt a network request while MT5 is tearing down would add deployment
risk without improving signal, order or trade safety.

Future EA work may explicitly skip the network call for `REASON_CLOSE` and log
`DEINIT_WEBHOOK_SKIPPED_TERMINAL_CLOSE`, or implement a durable startup-side
reconciliation mechanism. That work is outside this repair and must not be
coupled to strategy changes.

## Closed scope

This closure confirms:

- lifecycle normalization and persistence in Worker 3.3.1;
- organic `EA -> Worker -> Supabase` initialization evidence;
- strict separation of v4.43.0 REAL and v4.43.1 SHADOW_ONLY;
- deterministic request correlation and no duplicate lifecycle inserts;
- `ea_deinit` terminal-close failure classified as non-blocking;
- no synthetic production webhook, schema, RLS, strategy or capital change.

This closure does not validate a new H4 signal evaluation, an order, a trade
open/close event or a strategy promotion.
