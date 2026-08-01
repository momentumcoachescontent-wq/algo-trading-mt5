import {
  firstDefined,
  normalizeExecutionScope,
  toBoolean,
  toNumber,
  toText,
} from "./observability";
import type { Payload } from "./observability";

export type LifecycleEvent = "ea_init" | "ea_deinit";

function parseScope(value: unknown): Payload {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return { ...(value as Payload) };
  }
  if (typeof value !== "string") return {};
  try {
    const parsed: unknown = JSON.parse(value);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? { ...(parsed as Payload) }
      : {};
  } catch {
    return {};
  }
}

function setIfMissing(row: Payload, key: string, value: unknown): void {
  if (value === null || value === undefined || value === "") return;
  if (row[key] === null || row[key] === undefined || row[key] === "") {
    row[key] = value;
  }
}

export function buildLifecycleExecutionScope(body: Payload): Payload | null {
  const scope = parseScope(body.execution_scope);
  const normalized = normalizeExecutionScope(body);

  setIfMissing(
    scope,
    "mode",
    toText(
      firstDefined(
        scope.mode,
        scope.execution_mode,
        scope.scope_mode,
        normalized.mode,
        body.execution_mode,
        body.scope_mode,
        body.mode,
      ),
    ),
  );
  setIfMissing(scope, "capital_enabled", normalized.capitalEnabled);
  setIfMissing(scope, "order_send_allowed", normalized.orderSendAllowed);
  setIfMissing(scope, "shadow_only", normalized.shadowOnly);
  setIfMissing(scope, "policy_name", normalized.policyName);
  setIfMissing(scope, "reason", normalized.reason);
  setIfMissing(
    scope,
    "symbol_real_allowed",
    toBoolean(firstDefined(scope.symbol_real_allowed, body.symbol_real_allowed)),
  );
  setIfMissing(
    scope,
    "reason_code",
    toText(firstDefined(scope.reason_code, body.reason_code)),
  );

  return Object.keys(scope).length > 0 ? scope : null;
}

export function buildLifecycleRow(
  body: Payload,
  event: LifecycleEvent,
  requestId: string,
  receivedAt = new Date().toISOString(),
): Payload {
  const scope = buildLifecycleExecutionScope(body);
  const executionMode = toText(
    firstDefined(scope?.mode, body.execution_mode, body.scope_mode, body.mode),
  );

  return {
    event,
    symbol: body.symbol,
    ea_version: body.ea_version,
    phase: body.phase ?? null,
    balance: toNumber(body.balance),
    ts: receivedAt,
    deinit_reason_code:
      event === "ea_deinit"
        ? toNumber(firstDefined(body.deinit_reason_code, body.reason_code))
        : null,
    deinit_reason_text:
      event === "ea_deinit"
        ? toText(
            firstDefined(body.deinit_reason_text, body.reason_text, body.reason),
          )
        : null,
    boot_id: toText(body.boot_id),
    terminal_time: toText(
      firstDefined(
        body.terminal_time,
        body.terminal_ts,
        body.event_time,
        body.timestamp,
      ),
    ),
    guard_version: toText(body.guard_version),
    execution_mode: executionMode,
    execution_scope: scope,
    raw_payload: {
      ...body,
      normalized_event: event,
      worker_request_id: requestId,
      worker_received_at: receivedAt,
    },
    request_id: requestId,
  };
}
