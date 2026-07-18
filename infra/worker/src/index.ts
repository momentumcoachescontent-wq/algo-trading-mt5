/**
 * Cloudflare Worker — algo-trading-mt5
 * v3.3.0 — Stage10C observability and trade-linking repair
 *
 * This release changes persistence semantics only. It does not change strategy,
 * risk, signals, order authorization, or EA parameters.
 */

import { Hono } from "hono";
import {
  buildSignalObservability,
  firstDefined,
  normalizeTradeIdentity,
  toNumber,
  toText,
} from "./observability";
import type { Payload, TradeEvent } from "./observability";

type EventType =
  | "trade_open"
  | "trade_close"
  | "signal_eval"
  | "circuit_break"
  | "ea_init"
  | "ea_deinit";

const SUPPORTED_EVENTS = new Set<EventType>([
  "trade_open",
  "trade_close",
  "signal_eval",
  "circuit_break",
  "ea_init",
  "ea_deinit",
]);
const TRADE_EVENTS = new Set<EventType>(["trade_open", "trade_close"]);

interface Env {
  SUPABASE_URL: string;
  SUPABASE_ANON_KEY?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  EA_WEBHOOK_SECRET: string;
}

interface ValidationResult {
  ok: boolean;
  error?: string;
}

interface OpenTradeCandidate {
  id: string | number;
  execution_mode?: string | null;
  strategy_variant?: string | null;
}

function makeRequestId(): string {
  return crypto.randomUUID().slice(0, 8);
}

function getSupabaseKey(env: Env): string | undefined {
  return env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY;
}

function normalizeEvent(raw: unknown): EventType {
  const event = String(raw ?? "").trim();
  if (event === "open") return "trade_open";
  if (event === "close") return "trade_close";
  if (event === "init") return "ea_init";
  if (event === "deinit") return "ea_deinit";
  return event as EventType;
}

function normalizeDirection(raw?: unknown): "buy" | "sell" | null {
  if (raw == null || raw === "") return null;
  const value = String(raw).trim().toLowerCase();
  if (
    value === "buy" ||
    value === "buy_closed" ||
    value === "long" ||
    value.endsWith("_buy") ||
    value.includes("buy")
  ) {
    return "buy";
  }
  if (
    value === "sell" ||
    value === "sell_closed" ||
    value === "short" ||
    value.endsWith("_sell") ||
    value.includes("sell")
  ) {
    return "sell";
  }
  return null;
}

function supabaseHeaders(key: string, prefer = "return=minimal"): HeadersInit {
  return {
    "Content-Type": "application/json",
    apikey: key,
    Authorization: `Bearer ${key}`,
    Prefer: prefer,
    "Accept-Profile": "public",
    "Content-Profile": "public",
  };
}

function buildRawPayload(
  body: Payload,
  normalizedEvent: EventType,
  requestId: string,
): Payload {
  return {
    ...body,
    normalized_event: normalizedEvent,
    worker_request_id: requestId,
    worker_received_at: new Date().toISOString(),
  };
}

function validatePayload(body: Payload): ValidationResult {
  if (!body.event) return { ok: false, error: "Campo 'event' requerido" };
  const event = normalizeEvent(body.event);
  if (!SUPPORTED_EVENTS.has(event)) {
    return { ok: false, error: `Evento no soportado: '${String(body.event)}'` };
  }
  if (!body.symbol) return { ok: false, error: "Campo 'symbol' requerido" };
  if (!body.ea_version) return { ok: false, error: "Campo 'ea_version' requerido" };

  if (TRADE_EVENTS.has(event)) {
    if (!body.direction) {
      return { ok: false, error: "Campo 'direction' requerido para trade_open/trade_close" };
    }
    if (body.lots == null && body.volume == null) {
      return { ok: false, error: "Campo 'lots' requerido para trade_open/trade_close" };
    }
    if (
      body.ticket == null &&
      body.order_ticket == null &&
      body.deal_ticket == null &&
      body.position_id == null
    ) {
      return {
        ok: false,
        error:
          "Se requiere ticket, order_ticket, deal_ticket o position_id para trade_open/trade_close",
      };
    }
  }
  return { ok: true };
}

const app = new Hono<{ Bindings: Env }>();

app.get("/trading/health", (c) =>
  c.json({
    status: "ok",
    version: "3.3.0-stage10c-observability",
    ts: new Date().toISOString(),
  }),
);

app.use("/trading/webhook", async (c, next) => {
  const requestId = makeRequestId();
  const provided = c.req.header("X-EA-Secret");
  const expected = c.env.EA_WEBHOOK_SECRET;

  if (!provided) {
    console.log(
      `[AUTH_FAIL] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        reason: "missing_header",
        provided: "missing",
      })}`,
    );
    return c.json({ requestId, error: "Unauthorized", reason: "missing_header" }, 401);
  }
  if (!expected) {
    console.log(
      `[AUTH_FAIL] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        reason: "missing_env_secret",
        env: "EA_WEBHOOK_SECRET missing",
      })}`,
    );
    return c.json({ requestId, error: "Unauthorized", reason: "missing_env_secret" }, 401);
  }
  if (provided !== expected) {
    console.log(
      `[AUTH_FAIL] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        reason: "secret_mismatch",
        provided: "mismatch",
      })}`,
    );
    return c.json({ requestId, error: "Unauthorized", reason: "secret_mismatch" }, 401);
  }
  await next();
});

app.post("/trading/webhook", async (c) => {
  const requestId = makeRequestId();
  const startMs = Date.now();

  let body: Payload;
  try {
    body = await c.req.json();
  } catch {
    console.log(
      `[VAL_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        error: "JSON inválido",
      })}`,
    );
    return c.json({ requestId, error: "JSON inválido" }, 400);
  }

  const validation = validatePayload(body);
  if (!validation.ok) {
    console.log(
      `[VAL_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        error: validation.error,
        event: body.event ?? null,
        symbol: body.symbol ?? null,
      })}`,
    );
    return c.json({ requestId, error: validation.error }, 400);
  }

  const event = normalizeEvent(body.event);
  console.log(
    `[WEBHOOK_PARSED] ${JSON.stringify({
      requestId,
      path: "/trading/webhook",
      event,
      raw_event: body.event ?? null,
      ticket: body.ticket ?? null,
      order_ticket: body.order_ticket ?? null,
      deal_ticket: body.deal_ticket ?? null,
      position_id: body.position_id ?? null,
      signal_eval_id: body.signal_eval_id ?? null,
      symbol: body.symbol ?? null,
      direction: body.direction ?? null,
      action: body.action ?? null,
      ea_version: body.ea_version ?? null,
      phase: body.phase ?? null,
    })}`,
  );

  const supabaseUrl = c.env.SUPABASE_URL;
  const supabaseKey = getSupabaseKey(c.env);
  if (!supabaseUrl || !supabaseKey) {
    const error = !supabaseUrl ? "SUPABASE_URL missing" : "No Supabase key configured";
    console.log(`[CONFIG_ERROR] ${JSON.stringify({ requestId, error })}`);
    return c.json({ requestId, error }, 500);
  }

  try {
    if (event === "trade_open" || event === "trade_close") {
      await handleTradeEvent(body, event, supabaseUrl, supabaseKey, requestId);
    } else if (event === "signal_eval") {
      await handleSignalEval(body, event, supabaseUrl, supabaseKey, requestId);
    } else if (event === "circuit_break") {
      await handleCircuitBreak(body, supabaseUrl, supabaseKey, requestId);
    } else if (event === "ea_init" || event === "ea_deinit") {
      await handleLifecycle(body, event, supabaseUrl, supabaseKey, requestId);
    }
  } catch (err) {
    const ms = Date.now() - startMs;
    const error = err instanceof Error ? err.message : String(err);
    console.log(
      `[WORKER_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        event,
        error,
      })}`,
    );
    console.log(`[RES] ${JSON.stringify({ requestId, status: 500, ms })}`);
    return c.json({ requestId, error }, 500);
  }

  const ms = Date.now() - startMs;
  console.log(`[RES] ${JSON.stringify({ requestId, status: 200, ms })}`);
  return c.json({ requestId, ok: true, event, ms }, 200);
});

async function handleTradeEvent(
  body: Payload,
  event: TradeEvent,
  supabaseUrl: string,
  key: string,
  requestId: string,
): Promise<void> {
  const direction = normalizeDirection(body.direction);
  if (!direction) throw new Error(`direction inválido: '${String(body.direction)}'`);

  const identity = normalizeTradeIdentity(body, event);
  const lots = toNumber(firstDefined(body.lots, body.volume));
  const rawPayload = buildRawPayload(body, event, requestId);

  if (event === "trade_open") {
    const row: Payload = {
      ticket: identity.ticket,
      order_ticket: identity.orderTicket,
      deal_ticket: identity.dealTicket,
      position_id: identity.positionId,
      signal_eval_id: identity.signalEvalId,
      symbol: body.symbol,
      direction,
      open_time: firstDefined(
        body.open_time,
        body.entry_time,
        body.eval_time,
        new Date().toISOString(),
      ),
      close_time: null,
      open_price: toNumber(firstDefined(body.open_price, body.entry_price, body.price)),
      close_price: null,
      sl: toNumber(firstDefined(body.sl, body.sl_price)),
      tp: toNumber(firstDefined(body.tp, body.tp_price)),
      lots,
      pnl: null,
      close_reason: null,
      dd_pct: toNumber(body.dd_pct),
      phase: body.phase ?? null,
      ea_version: body.ea_version,
      event_type: "open",
      execution_mode: identity.executionMode,
      strategy_variant: identity.strategyVariant,
      guard_version: identity.guardVersion,
      magic_number: identity.magicNumber,
      boot_id: identity.bootId,
      link_status: identity.linkStatus,
      raw_payload: rawPayload,
    };
    await requireInsert(supabaseUrl, key, "trades", row, requestId);
    return;
  }

  const closeTime = firstDefined(
    body.close_time,
    body.exit_time,
    body.time,
    new Date().toISOString(),
  );
  const closePatch: Payload = {
    ticket: identity.ticket,
    order_ticket: identity.orderTicket,
    deal_ticket: identity.dealTicket,
    signal_eval_id: identity.signalEvalId,
    close_time: closeTime,
    close_price: toNumber(firstDefined(body.close_price, body.exit_price, body.price)),
    pnl: toNumber(body.pnl),
    close_reason: firstDefined(body.close_reason, body.reason, body.deal_reason),
    event_type: "close",
    execution_mode: identity.executionMode,
    strategy_variant: identity.strategyVariant,
    guard_version: identity.guardVersion,
    magic_number: identity.magicNumber,
    boot_id: identity.bootId,
    link_status: identity.positionId ? "CLOSED_LINKED_POSITION" : identity.linkStatus,
    raw_payload: rawPayload,
  };
  if (lots != null) closePatch.lots = lots;

  const patchResult = await patchSingleOpenTrade(
    supabaseUrl,
    key,
    identity.positionId,
    toText(body.symbol),
    identity.executionMode,
    identity.strategyVariant,
    closePatch,
    requestId,
  );
  if (patchResult.updated) return;

  // Preserve the close event without pretending that a missing link was resolved.
  const fallbackRow: Payload = {
    ticket: identity.ticket,
    order_ticket: identity.orderTicket,
    deal_ticket: identity.dealTicket,
    position_id: identity.positionId,
    signal_eval_id: identity.signalEvalId,
    symbol: body.symbol,
    direction,
    open_time: firstDefined(body.open_time, body.entry_time, closeTime),
    close_time: closeTime,
    open_price: toNumber(firstDefined(body.open_price, body.entry_price)),
    close_price: closePatch.close_price,
    sl: toNumber(firstDefined(body.sl, body.sl_price)),
    tp: toNumber(firstDefined(body.tp, body.tp_price)),
    lots,
    pnl: closePatch.pnl,
    close_reason: closePatch.close_reason,
    dd_pct: toNumber(body.dd_pct),
    phase: body.phase ?? null,
    ea_version: body.ea_version,
    event_type: "close",
    execution_mode: identity.executionMode,
    strategy_variant: identity.strategyVariant,
    guard_version: identity.guardVersion,
    magic_number: identity.magicNumber,
    boot_id: identity.bootId,
    link_status: "FALLBACK_UNMATCHED_CLOSE",
    raw_payload: rawPayload,
  };
  await requireInsert(supabaseUrl, key, "trades", fallbackRow, requestId);
  console.log(
    `[TRADE_CLOSE_FALLBACK_INSERTED] ${JSON.stringify({
      requestId,
      position_id: identity.positionId,
      deal_ticket: identity.dealTicket,
      symbol: body.symbol,
    })}`,
  );
}

async function handleSignalEval(
  body: Payload,
  event: EventType,
  supabaseUrl: string,
  key: string,
  requestId: string,
): Promise<void> {
  const rawDirection = firstDefined(
    body.direction,
    body.signal_direction,
    body.order_direction,
    body.action,
  );
  const observability = buildSignalObservability(body);
  const row: Payload = {
    symbol: body.symbol,
    eval_time: body.eval_time ?? new Date().toISOString(),
    bar_h4: observability.barH4,
    signal_eval_id: observability.signalEvalId,
    decision: observability.decision,
    technical_signal_status: observability.technicalSignalStatus,
    execution_mode: observability.executionMode,
    order_send_allowed: observability.orderSendAllowed,
    would_have_traded: observability.wouldHaveTraded,
    primary_signal_reason: observability.reasons.primarySignalReason,
    governance_guard_reason: observability.reasons.governanceGuardReason,
    execution_denied_reason: observability.reasons.executionDeniedReason,
    policy_name: observability.policyName,
    strategy_variant: observability.strategyVariant,
    guard_version: observability.guardVersion,
    magic_number: observability.magicNumber,
    boot_id: observability.bootId,
    bias_d1: toNumber(body.bias_d1) ?? 0,
    h4_signal: toNumber(body.h4_signal) ?? 0,
    compressed: body.compressed ?? false,
    comp_ratio: toNumber(body.comp_ratio),
    cb_ok: body.cb_ok ?? true,
    dd_day_pct: toNumber(body.dd_day_pct),
    block_reason: body.block_reason ?? null,
    action: body.action ?? null,
    ea_version: body.ea_version,
    phase: body.phase ?? null,
    raw_payload: buildRawPayload(body, event, requestId),
    direction: normalizeDirection(rawDirection),
    entry_price: toNumber(firstDefined(body.entry_price, body.open_price, body.price)),
    sl_price: toNumber(firstDefined(body.sl_price, body.sl)),
    tp_price: toNumber(firstDefined(body.tp_price, body.tp)),
    atr_h4: toNumber(firstDefined(body.atr_h4, body.atr)),
    distance_to_ema_atr: toNumber(
      firstDefined(body.distance_to_ema_atr, body.dist_ema_atr),
    ),
    trend_state: toText(body.trend_state),
    volatility_state: toText(body.volatility_state),
    session: toText(body.session),
  };

  // A persisted signal is required for reliable signal -> trade linking. Do not
  // return HTTP 200 when Supabase rejected the evidence.
  await requireInsert(supabaseUrl, key, "signal_evals", row, requestId);
}

async function handleCircuitBreak(
  body: Payload,
  supabaseUrl: string,
  key: string,
  requestId: string,
): Promise<void> {
  const row = {
    symbol: body.symbol,
    reason: body.reason ?? "pausa_DD_diario",
    dd_pct: toNumber(body.dd_pct),
    activated_at: body.activated_at ?? new Date().toISOString(),
    ea_version: body.ea_version,
    phase: body.phase ?? null,
  };
  const url = `${supabaseUrl}/rest/v1/circuit_breaks?on_conflict=symbol,date_trunc_day`;
  const res = await fetch(url, {
    method: "POST",
    headers: supabaseHeaders(key, "resolution=ignore-duplicates,return=minimal"),
    body: JSON.stringify(row),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.log(`[CIRCUIT_BREAK_WARN] ${JSON.stringify({ requestId, status: res.status, detail, row })}`);
  }
}

async function handleLifecycle(
  body: Payload,
  event: EventType,
  supabaseUrl: string,
  key: string,
  requestId: string,
): Promise<void> {
  const row = {
    event,
    symbol: body.symbol,
    ea_version: body.ea_version,
    phase: body.phase ?? null,
    balance: toNumber(body.balance),
    ts: new Date().toISOString(),
  };
  const res = await supabaseInsert(supabaseUrl, key, "ea_events", row, requestId);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.log(`[EA_EVENT_WARN] ${JSON.stringify({ requestId, status: res.status, detail, row })}`);
  }
}

async function supabaseInsert(
  supabaseUrl: string,
  key: string,
  table: string,
  row: Payload,
  requestId: string,
): Promise<Response> {
  const url = `${supabaseUrl}/rest/v1/${table}`;
  const res = await fetch(url, {
    method: "POST",
    headers: supabaseHeaders(key),
    body: JSON.stringify(row),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.log(
      `[SUPABASE_INSERT_ERROR] ${JSON.stringify({
        requestId,
        table,
        status: res.status,
        detail,
        payload: row,
      })}`,
    );
  }
  return res;
}

async function requireInsert(
  supabaseUrl: string,
  key: string,
  table: string,
  row: Payload,
  requestId: string,
): Promise<void> {
  const res = await supabaseInsert(supabaseUrl, key, table, row, requestId);
  if (!res.ok) throw new Error(`Supabase ${table} insert failed: ${res.status}`);
}

async function findOpenTradeCandidates(
  supabaseUrl: string,
  key: string,
  positionId: unknown,
  symbol: string | null,
  requestId: string,
): Promise<OpenTradeCandidate[]> {
  if (positionId == null || positionId === "" || !symbol) return [];
  const query = [
    "select=id,execution_mode,strategy_variant",
    `position_id=eq.${encodeURIComponent(String(positionId))}`,
    `symbol=eq.${encodeURIComponent(symbol)}`,
    "close_time=is.null",
    "limit=3",
  ].join("&");
  const res = await fetch(`${supabaseUrl}/rest/v1/trades?${query}`, {
    method: "GET",
    headers: supabaseHeaders(key, "return=representation"),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.log(
      `[SUPABASE_MATCH_ERROR] ${JSON.stringify({
        requestId,
        positionId,
        symbol,
        status: res.status,
        detail,
      })}`,
    );
    throw new Error(`Supabase trade match failed: ${res.status}`);
  }
  const rows: unknown = await res.json().catch(() => []);
  return Array.isArray(rows) ? (rows as OpenTradeCandidate[]) : [];
}

function chooseSingleCandidate(
  candidates: OpenTradeCandidate[],
  executionMode: string | null,
  strategyVariant: string | null,
): OpenTradeCandidate | null {
  if (candidates.length === 0) return null;
  const exact = candidates.filter((candidate) => {
    const modeMatches = !executionMode || candidate.execution_mode === executionMode;
    const variantMatches = !strategyVariant || candidate.strategy_variant === strategyVariant;
    return modeMatches && variantMatches;
  });
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) throw new Error("Ambiguous open-trade link: multiple exact candidates");
  if (candidates.length === 1) return candidates[0]; // legacy row without new metadata
  throw new Error("Ambiguous open-trade link: multiple legacy candidates");
}

async function patchSingleOpenTrade(
  supabaseUrl: string,
  key: string,
  positionId: unknown,
  symbol: string | null,
  executionMode: string | null,
  strategyVariant: string | null,
  patch: Payload,
  requestId: string,
): Promise<{ updated: boolean }> {
  const candidates = await findOpenTradeCandidates(
    supabaseUrl,
    key,
    positionId,
    symbol,
    requestId,
  );
  const candidate = chooseSingleCandidate(candidates, executionMode, strategyVariant);
  if (!candidate) return { updated: false };

  const url = `${supabaseUrl}/rest/v1/trades?id=eq.${encodeURIComponent(
    String(candidate.id),
  )}&close_time=is.null`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: supabaseHeaders(key, "return=representation"),
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.log(
      `[SUPABASE_PATCH_ERROR] ${JSON.stringify({
        requestId,
        table: "trades",
        tradeId: candidate.id,
        status: res.status,
        detail,
      })}`,
    );
    throw new Error(`Supabase trades patch failed: ${res.status}`);
  }
  const rows: unknown = await res.json().catch(() => []);
  const updatedRows = Array.isArray(rows) ? rows.length : 0;
  if (updatedRows !== 1) {
    throw new Error(`Expected one patched trade row; observed ${updatedRows}`);
  }
  console.log(
    `[SUPABASE_PATCH_RESULT] ${JSON.stringify({
      requestId,
      table: "trades",
      tradeId: candidate.id,
      positionId,
      updated: true,
    })}`,
  );
  return { updated: true };
}

export default app;
