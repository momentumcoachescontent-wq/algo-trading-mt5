/**
 * Cloudflare Worker — algo-trading-mt5
 * v3.2.1 — BUG-DATA-01 persistence repair
 *
 * Objetivo F5A:
 *  - Persistir raw_payload y Edge Context Layer en signal_evals.
 *  - Persistir datos completos de apertura/cierre en trades.
 *  - Actualizar el trade abierto en trade_close usando position_id antes de crear fallback.
 *  - Mantener compatibilidad con eventos legacy: open/close/init/deinit.
 *  - Mantener inserts REST con Accept-Profile/Content-Profile public.
 *
 * No cambia estrategia, riesgo, señales ni parámetros del EA.
 */

import { Hono } from "hono";

// ── Tipos de evento y sus campos requeridos ──────────────────────────────
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

// Solo trade_open y trade_close necesitan direction, lots y ticket.
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

// ── Helpers generales ───────────────────────────────────────────────────
function makeRequestId(): string {
  return crypto.randomUUID().slice(0, 8);
}

function getSupabaseKey(env: Env): string | undefined {
  return env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY;
}

function normalizeEvent(raw: unknown): EventType {
  const event = String(raw ?? "").trim();

  // Compatibilidad con Logger legacy F4/v2.x.
  if (event === "open") return "trade_open";
  if (event === "close") return "trade_close";
  if (event === "init") return "ea_init";
  if (event === "deinit") return "ea_deinit";

  return event as EventType;
}

function normalizeSession(raw: unknown): string | null {
  const value = toStringOrNull(raw)?.trim().toUpperCase();
  if (!value) return null;

  if (value === "OFFHOURS") return "OFF_HOURS";

  return value;
}

// Normaliza direction para Supabase: buy | sell.
// Acepta variantes MQL5/EA: BUY, SELL, buy_closed, ENTRY_READY_BUY, etc.
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

function resolveEventType(event: string, direction?: unknown): "open" | "close" | string {
  const rawDirection = String(direction ?? "").toLowerCase();
  if (event === "trade_close" || rawDirection.endsWith("_closed")) return "close";
  if (event === "trade_open") return "open";
  return event;
}

function toNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function toStringOrNull(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function toBoolean(value: unknown): boolean | null {
  if (value == null || value === "") return null;

  if (typeof value === "boolean") return value;

  const normalized = String(value).trim().toLowerCase();

  if (normalized === "true" || normalized === "1" || normalized === "yes") return true;
  if (normalized === "false" || normalized === "0" || normalized === "no") return false;

  return null;
}

function firstDefined(...values: unknown[]): unknown {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

function supabaseHeaders(key: string, prefer = "return=minimal"): HeadersInit {
  return {
    "Content-Type": "application/json",
    "apikey": key,
    "Authorization": `Bearer ${key}`,
    "Prefer": prefer,
    "Accept-Profile": "public",
    "Content-Profile": "public",
  };
}

function buildRawPayload(
  body: Record<string, unknown>,
  normalizedEvent: EventType,
  requestId: string
): Record<string, unknown> {
  return {
    ...body,
    normalized_event: normalizedEvent,
    worker_request_id: requestId,
    worker_received_at: new Date().toISOString(),
  };
}

// ── Validación por tipo de evento ────────────────────────────────────────
function validatePayload(body: Record<string, unknown>): ValidationResult {
  if (!body.event) return { ok: false, error: "Campo 'event' requerido" };

  const event = normalizeEvent(body.event);
  if (!SUPPORTED_EVENTS.has(event)) {
    return { ok: false, error: `Evento no soportado: '${String(body.event)}'` };
  }

  if (!body.symbol) return { ok: false, error: "Campo 'symbol' requerido" };
  if (!body.ea_version) return { ok: false, error: "Campo 'ea_version' requerido" };

  if (TRADE_EVENTS.has(event)) {
    if (!body.direction) return { ok: false, error: "Campo 'direction' requerido para trade_open/trade_close" };
    if (body.lots == null && body.volume == null) {
      return { ok: false, error: "Campo 'lots' requerido para trade_open/trade_close" };
    }
    if (body.ticket == null && body.position_id == null) {
      return { ok: false, error: "Campo 'ticket' o 'position_id' requerido para trade_open/trade_close" };
    }
  }

  return { ok: true };
}

// ── App ──────────────────────────────────────────────────────────────────
const app = new Hono<{ Bindings: Env }>();

// ── Health público ───────────────────────────────────────────────────────
app.get("/trading/health", (c) =>
  c.json({
    status: "ok",
    version: "3.2.1-bug-data-01b-touch-zone",
    ts: new Date().toISOString(),
  })
);

// ── Auth middleware solo para webhook ────────────────────────────────────
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
      })}`
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
      })}`
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
      })}`
    );
    return c.json({ requestId, error: "Unauthorized", reason: "secret_mismatch" }, 401);
  }

  await next();
});

// ── Webhook principal ────────────────────────────────────────────────────
app.post("/trading/webhook", async (c) => {
  const requestId = makeRequestId();
  const startMs = Date.now();

  let body: Record<string, unknown>;
  try {
    body = await c.req.json();
  } catch {
    console.log(
      `[VAL_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        error: "JSON inválido",
      })}`
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
      })}`
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
      position_id: body.position_id ?? null,
      symbol: body.symbol ?? null,
      direction: body.direction ?? null,
      action: body.action ?? null,
      pnl: body.pnl ?? null,
      ea_version: body.ea_version ?? null,
      phase: body.phase ?? null,
    })}`
  );

  const supabaseUrl = c.env.SUPABASE_URL;
  const supabaseKey = getSupabaseKey(c.env);

  if (!supabaseUrl) {
    const ms = Date.now() - startMs;
    console.log(
      `[CONFIG_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        error: "SUPABASE_URL missing",
      })}`
    );
    console.log(`[RES] ${JSON.stringify({ requestId, path: "/trading/webhook", status: 500, ms })}`);
    return c.json({ requestId, error: "SUPABASE_URL missing" }, 500);
  }

  if (!supabaseKey) {
    const ms = Date.now() - startMs;
    console.log(
      `[CONFIG_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        error: "No Supabase key configured",
      })}`
    );
    console.log(`[RES] ${JSON.stringify({ requestId, path: "/trading/webhook", status: 500, ms })}`);
    return c.json({ requestId, error: "No Supabase key configured" }, 500);
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
    console.log(
      `[WORKER_ERROR] ${JSON.stringify({
        requestId,
        path: "/trading/webhook",
        event,
        error: err instanceof Error ? err.message : String(err),
      })}`
    );
    console.log(`[RES] ${JSON.stringify({ requestId, path: "/trading/webhook", status: 500, ms })}`);
    return c.json({ requestId, error: err instanceof Error ? err.message : String(err) }, 500);
  }

  const ms = Date.now() - startMs;
  console.log(`[RES] ${JSON.stringify({ requestId, path: "/trading/webhook", status: 200, ms })}`);
  return c.json({ requestId, ok: true, event, ms }, 200);
});

// ── Handler: trade_open / trade_close ────────────────────────────────────
async function handleTradeEvent(
  body: Record<string, unknown>,
  event: EventType,
  supabaseUrl: string,
  key: string,
  requestId: string
): Promise<void> {
  const rawDirection = body.direction;
  const direction = normalizeDirection(rawDirection);

  if (!direction) {
    throw new Error(`direction inválido: '${String(rawDirection)}'`);
  }

  const eventType = resolveEventType(event, rawDirection);
  const positionId = firstDefined(body.position_id, body.ticket);
  const ticket = firstDefined(body.ticket, body.position_id);
  const lots = toNumber(firstDefined(body.lots, body.volume));

  if (eventType === "open") {
    const row = {
      ticket,
      position_id: positionId,
      symbol: body.symbol,
      direction,
      open_time: firstDefined(body.open_time, body.entry_time, body.eval_time, new Date().toISOString()),
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
    };

    const res = await supabaseInsert(supabaseUrl, key, "trades", row, requestId);
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      console.log(
        `[SUPABASE_ERROR] ${JSON.stringify({
          requestId,
          table: "trades",
          status: res.status,
          detail,
          row,
        })}`
      );
      throw new Error(`Supabase trades insert failed: ${res.status}`);
    }

    return;
  }

  const closePatch: Record<string, unknown> = {
    close_time: firstDefined(body.close_time, body.exit_time, body.time, new Date().toISOString()),
    close_price: toNumber(firstDefined(body.close_price, body.exit_price, body.price)),
    pnl: toNumber(body.pnl),
    close_reason: firstDefined(body.close_reason, body.reason, body.deal_reason),
    event_type: "close",
  };

  if (lots != null) closePatch.lots = lots;

  const patchResult = await supabasePatchOpenTrade(
    supabaseUrl,
    key,
    positionId,
    closePatch,
    requestId
  );

  if (patchResult.updated) return;

  // Fallback defensivo: si no existe una fila abierta por position_id, registra el cierre
  // para no perder evidencia operativa. Esto debe investigarse si ocurre.
  const fallbackRow = {
    ticket,
    position_id: positionId,
    symbol: body.symbol,
    direction,
    open_time: firstDefined(body.open_time, body.entry_time, null),
    close_time: closePatch.close_time,
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
  };

  const fallbackRes = await supabaseInsert(supabaseUrl, key, "trades", fallbackRow, requestId);
  if (!fallbackRes.ok) {
    const detail = await fallbackRes.text().catch(() => "");
    console.log(
      `[SUPABASE_ERROR] ${JSON.stringify({
        requestId,
        table: "trades",
        status: fallbackRes.status,
        detail,
        fallbackRow,
      })}`
    );
    throw new Error(`Supabase trades close fallback insert failed: ${fallbackRes.status}`);
  }

  console.log(
    `[TRADE_CLOSE_FALLBACK_INSERTED] ${JSON.stringify({
      requestId,
      position_id: positionId,
      ticket,
      symbol: body.symbol,
    })}`
  );
}

// ── Handler: signal_eval ─────────────────────────────────────────────────
async function handleSignalEval(
  body: Record<string, unknown>,
  event: EventType,
  supabaseUrl: string,
  key: string,
  requestId: string
): Promise<void> {
  const rawDirection = firstDefined(
    body.direction,
    body.signal_direction,
    body.order_direction,
    body.action
  );

  const row = {
    symbol: body.symbol,
    eval_time: body.eval_time ?? new Date().toISOString(),
    d1_bias: toNumber(firstDefined(
      body.bias_d1,
      body.bias_d1_score,
      body.d1_bias_score,
      body.d1BiasScore,
      body.d1_bias,
      body.d1Bias,
      body.biasD1
    )),
    h4_signal: toNumber(body.h4_signal) ?? 0,
    compressed: body.compressed ?? false,
    comp_ratio: toNumber(body.comp_ratio),
    cb_ok: body.cb_ok ?? true,
    dd_day_pct: toNumber(body.dd_day_pct),
    block_reason: body.block_reason ?? null,
    action: body.action ?? null,
    ea_version: body.ea_version,
    phase: body.phase ?? null,

    // BUG-DATA-01: raw payload y contexto completo.
    raw_payload: buildRawPayload(body, event, requestId),
    direction: normalizeDirection(rawDirection),
    entry_price: toNumber(firstDefined(body.entry_price, body.open_price, body.price)),
    sl_price: toNumber(firstDefined(body.sl_price, body.sl)),
    tp_price: toNumber(firstDefined(body.tp_price, body.tp)),
    atr_h4: toNumber(firstDefined(body.atr_h4, body.atr)),
    distance_to_ema_atr: toNumber(firstDefined(body.distance_to_ema_atr, body.dist_ema_atr)),
    touch_zone: toBoolean(firstDefined(body.touch_zone, body.touchZone)),
    trend_state: toStringOrNull(firstDefined(body.trend_state, body.trend)),
    volatility_state: toStringOrNull(firstDefined(body.volatility_state, body.volatility)),
    session: normalizeSession(firstDefined(body.session, body.session_name)),
    spread_atr_ratio: toNumber(body.spread_atr_ratio),
    atr_energy: toNumber(firstDefined(
      body.atr_energy,
      body.atr_energy_ratio,
      body.atrEnergy,
      body.atrEnergyRatio
    )),
    atr_energy_ratio: toNumber(firstDefined(
      body.atr_energy_ratio,
      body.atr_energy,
      body.atrEnergyRatio,
      body.atrEnergy
    )),
    atr_energy_score: toNumber(firstDefined(
      body.atr_energy_score,
      body.atrEnergyScore
    )),
    guard_version: toStringOrNull(body.guard_version),
    execution_guard_triggered: body.execution_guard_triggered ?? false,
    execution_guard_reason: toStringOrNull(firstDefined(
      body.execution_guard_reason,
      body.exec_guard_reason,
      body.block_reason
    )),
  };

  const res = await supabaseInsert(supabaseUrl, key, "signal_evals", row, requestId);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.log(
      `[SIGNAL_EVAL_ERROR] ${JSON.stringify({
        requestId,
        status: res.status,
        detail,
        row,
      })}`
    );

    throw new Error(`Supabase signal_evals insert failed: ${res.status} ${detail}`);
  }

  console.log(
    `[SIGNAL_EVAL_INSERT_OK] ${JSON.stringify({
      requestId,
      symbol: body.symbol,
      eval_time: body.eval_time ?? null,
      action: body.action ?? null,
      touch_zone: row.touch_zone,
      ea_version: body.ea_version ?? null,
    })}`
  );
}
// ── Handler: circuit_break ───────────────────────────────────────────────
async function handleCircuitBreak(
  body: Record<string, unknown>,
  supabaseUrl: string,
  key: string,
  requestId: string
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

// ── Handler: lifecycle (ea_init / ea_deinit) ─────────────────────────────
async function handleLifecycle(
  body: Record<string, unknown>,
  event: EventType,
  supabaseUrl: string,
  key: string,
  requestId: string
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

// ── Supabase helpers ─────────────────────────────────────────────────────
async function supabaseInsert(
  supabaseUrl: string,
  key: string,
  table: string,
  row: Record<string, unknown>,
  requestId: string
): Promise<Response> {
  const url = `${supabaseUrl}/rest/v1/${table}`;
  const res = await fetch(url, {
    method: "POST",
    headers: supabaseHeaders(key),
    body: JSON.stringify(row),
  });

  if (!res.ok) {
    const errText = await res.clone().text().catch(() => "");
    console.log(
      `[SUPABASE_INSERT_ERROR] ${JSON.stringify({
        requestId,
        table,
        status: res.status,
        detail: errText,
        payload: row,
      })}`
    );
  }

  return res;
}

async function supabasePatchOpenTrade(
  supabaseUrl: string,
  key: string,
  positionId: unknown,
  patch: Record<string, unknown>,
  requestId: string
): Promise<{ ok: boolean; updated: boolean }> {
  if (positionId == null || positionId === "") {
    return { ok: false, updated: false };
  }

  const encodedPositionId = encodeURIComponent(String(positionId));
  const url = `${supabaseUrl}/rest/v1/trades?position_id=eq.${encodedPositionId}&close_time=is.null`;

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
        status: res.status,
        detail,
        positionId,
        patch,
      })}`
    );
    return { ok: false, updated: false };
  }

  const rows = await res.json().catch(() => []);
  const updated = Array.isArray(rows) && rows.length > 0;

  console.log(
    `[SUPABASE_PATCH_RESULT] ${JSON.stringify({
      requestId,
      table: "trades",
      positionId,
      updated,
      rows: Array.isArray(rows) ? rows.length : null,
    })}`
  );

  return { ok: true, updated };
}

export default app;
