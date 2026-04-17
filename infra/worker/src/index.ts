/**
 * Cloudflare Worker — algo-trading-mt5
 * v3.1 — Fix estructural post-incidente 2026-04-16
 *
 * Cambios respecto a versión anterior:
 *  - BUG-01: Validación por tipo de evento (direction/lots opcionales en eval/circuit)
 *  - BUG-02: Normalización de direction antes de insertar en Supabase
 *  - BUG-04: Logging idempotente para circuit_break
 *  - BUG-05: open_time separado de close_time en payload de cierre
 *  - Nuevo:  Tabla signal_evals separada para auditoría de señales
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

// Solo trade_open y trade_close necesitan direction y lots
const TRADE_EVENTS = new Set<EventType>(["trade_open", "trade_close"]);

// Normaliza direction para Supabase (CHECK constraint: 'buy' | 'sell')
function normalizeDirection(raw: string): "buy" | "sell" | null {
  if (raw === "buy" || raw === "buy_closed") return "buy";
  if (raw === "sell" || raw === "sell_closed") return "sell";
  return null;
}

// Determina event_type limpio para la tabla trades
function resolveEventType(event: string, direction: string): string {
  if (event === "trade_close" || direction?.endsWith("_closed")) return "close";
  if (event === "trade_open") return "open";
  return event;
}

// ── Validación por tipo de evento ────────────────────────────────────────
interface ValidationResult {
  ok: boolean;
  error?: string;
}

function validatePayload(body: Record<string, unknown>): ValidationResult {
  const event = body.event as string;
  if (!event) return { ok: false, error: "Campo 'event' requerido" };
  if (!body.symbol) return { ok: false, error: "Campo 'symbol' requerido" };
  if (!body.ea_version) return { ok: false, error: "Campo 'ea_version' requerido" };

  // direction y lots solo son requeridos en eventos de trade
  if (TRADE_EVENTS.has(event as EventType)) {
    if (!body.direction) return { ok: false, error: "Campo 'direction' requerido para trade_open/close" };
    if (body.lots == null) return { ok: false, error: "Campo 'lots' requerido para trade_open/close" };
    if (body.ticket == null) return { ok: false, error: "Campo 'ticket' requerido para trade_open/close" };
  }

  return { ok: true };
}

// ── App ──────────────────────────────────────────────────────────────────
const app = new Hono<{ Bindings: Env }>();

interface Env {
  SUPABASE_URL: string;
  SUPABASE_ANON_KEY: string;
  EA_WEBHOOK_SECRET: string;
}

// ── Auth middleware ──────────────────────────────────────────────────────
app.use("/trading/*", async (c, next) => {
  const secret = c.req.header("X-EA-Secret");
  if (!secret || secret !== c.env.EA_WEBHOOK_SECRET) {
    return c.json({ error: "Unauthorized" }, 401);
  }
  await next();
});

// ── Health ───────────────────────────────────────────────────────────────
app.get("/trading/health", (c) =>
  c.json({ status: "ok", version: "3.1", ts: new Date().toISOString() })
);

// ── Webhook principal ────────────────────────────────────────────────────
app.post("/trading/webhook", async (c) => {
  const requestId = crypto.randomUUID().slice(0, 8);
  const startMs = Date.now();

  let body: Record<string, unknown>;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ requestId, error: "JSON inválido" }, 400);
  }

  // ── Validación por tipo de evento ──────────────────────────────────────
  const validation = validatePayload(body);
  if (!validation.ok) {
    console.log(
      `[VAL_ERROR] ${JSON.stringify({ requestId, error: validation.error, event: body.event, symbol: body.symbol })}`
    );
    return c.json({ requestId, error: validation.error }, 400);
  }

  const event = body.event as string;
  console.log(
    `[WEBHOOK_PARSED] ${JSON.stringify({ requestId, event, ticket: body.ticket, symbol: body.symbol, direction: body.direction, pnl: body.pnl, ea_version: body.ea_version, phase: body.phase })}`
  );

  const supabaseUrl = c.env.SUPABASE_URL;
  const supabaseAnonKey = c.env.SUPABASE_ANON_KEY;

  // ── Router por tipo de evento ──────────────────────────────────────────
  try {
    if (event === "trade_open" || event === "trade_close") {
      await handleTradeEvent(body, event, supabaseUrl, supabaseAnonKey, requestId);
    } else if (event === "signal_eval") {
      await handleSignalEval(body, supabaseUrl, supabaseAnonKey, requestId);
    } else if (event === "circuit_break") {
      await handleCircuitBreak(body, supabaseUrl, supabaseAnonKey, requestId);
    } else if (event === "ea_init" || event === "ea_deinit") {
      await handleLifecycle(body, event, supabaseUrl, supabaseAnonKey, requestId);
    }
    // Eventos desconocidos: loguear pero no fallar
  } catch (err) {
    const ms = Date.now() - startMs;
    console.log(`[RES] ${JSON.stringify({ requestId, path: "/trading/webhook", status: 500, ms })}`);
    return c.json({ requestId, error: String(err) }, 500);
  }

  const ms = Date.now() - startMs;
  console.log(`[RES] ${JSON.stringify({ requestId, path: "/trading/webhook", status: 200, ms })}`);
  return c.json({ requestId, ok: true, event, ms }, 200);
});

// ── Handler: trade_open / trade_close ────────────────────────────────────
async function handleTradeEvent(
  body: Record<string, unknown>,
  event: string,
  supabaseUrl: string,
  key: string,
  requestId: string
): Promise<void> {
  const rawDirection = body.direction as string;
  const direction = normalizeDirection(rawDirection);

  if (!direction) {
    throw new Error(`direction inválido: '${rawDirection}'`);
  }

  const eventType = resolveEventType(event, rawDirection);

  // BUG-05 fix: open_time real desde el payload, no duplicar con close_time
  const openTime = (body.open_time as string) ?? new Date().toISOString();
  const closeTime = eventType === "close"
    ? ((body.close_time as string) ?? new Date().toISOString())
    : null;

  const row = {
    ticket: body.ticket,
    position_id: body.position_id ?? body.ticket,
    symbol: body.symbol,
    direction,                      // ← normalizado: 'buy' o 'sell' siempre
    open_time: openTime,
    close_time: closeTime,
    open_price: body.open_price ?? null,
    close_price: body.close_price ?? null,
    sl: body.sl ?? 0,
    tp: body.tp ?? 0,
    lots: body.lots,
    pnl: body.pnl ?? null,
    dd_pct: body.dd_pct ?? null,
    phase: body.phase,
    ea_version: body.ea_version,
    event_type: eventType,
  };

  const res = await supabaseInsert(supabaseUrl, key, "trades", row, requestId);
  if (!res.ok) {
    const detail = await res.text();
    console.log(`[SUPABASE_ERROR] ${JSON.stringify({ requestId, status: res.status, detail })}`);
    throw new Error(`Supabase trades insert failed: ${res.status}`);
  }
}

// ── Handler: signal_eval ─────────────────────────────────────────────────
// Persiste en tabla separada signal_evals — no mezcla con trades
async function handleSignalEval(
  body: Record<string, unknown>,
  supabaseUrl: string,
  key: string,
  requestId: string
): Promise<void> {
  const row = {
    symbol: body.symbol,
    eval_time: body.eval_time ?? new Date().toISOString(),
    bias_d1: body.bias_d1 ?? 0,
    h4_signal: body.h4_signal ?? 0,
    compressed: body.compressed ?? false,
    comp_ratio: body.comp_ratio ?? null,
    cb_ok: body.cb_ok ?? true,
    dd_day_pct: body.dd_day_pct ?? null,
    block_reason: body.block_reason ?? null,
    action: body.action ?? null,
    ea_version: body.ea_version,
    phase: body.phase,
  };

  const res = await supabaseInsert(supabaseUrl, key, "signal_evals", row, requestId);
  if (!res.ok) {
    // signal_eval es best-effort — no fallar el webhook
    const detail = await res.text();
    console.log(`[SIGNAL_EVAL_WARN] ${JSON.stringify({ requestId, status: res.status, detail })}`);
  }
}

// ── Handler: circuit_break ───────────────────────────────────────────────
// BUG-04 fix: upsert con on_conflict para evitar inserciones duplicadas
async function handleCircuitBreak(
  body: Record<string, unknown>,
  supabaseUrl: string,
  key: string,
  requestId: string
): Promise<void> {
  const row = {
    symbol: body.symbol,
    reason: body.reason ?? "pausa_DD_diario",
    dd_pct: body.dd_pct ?? null,
    activated_at: body.activated_at ?? new Date().toISOString(),
    ea_version: body.ea_version,
    phase: body.phase,
  };

  // Upsert: si ya existe un circuit_break activo para este símbolo/día, no duplicar
  const url = `${supabaseUrl}/rest/v1/circuit_breaks?on_conflict=symbol,date_trunc_day`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "apikey": key,
      "Authorization": `Bearer ${key}`,
      "Prefer": "resolution=ignore-duplicates",
    },
    body: JSON.stringify(row),
  });

  if (!res.ok) {
    const detail = await res.text();
    // También best-effort
    console.log(`[CIRCUIT_BREAK_WARN] ${JSON.stringify({ requestId, status: res.status, detail })}`);
  }
}

// ── Handler: lifecycle (ea_init / ea_deinit) ─────────────────────────────
async function handleLifecycle(
  body: Record<string, unknown>,
  event: string,
  supabaseUrl: string,
  key: string,
  requestId: string
): Promise<void> {
  const row = {
    event,
    symbol: body.symbol,
    ea_version: body.ea_version,
    phase: body.phase,
    balance: body.balance ?? null,
    ts: new Date().toISOString(),
  };

  const res = await supabaseInsert(supabaseUrl, key, "ea_events", row, requestId);
  if (!res.ok) {
    const detail = await res.text();
    console.log(`[EA_EVENT_WARN] ${JSON.stringify({ requestId, status: res.status, detail })}`);
  }
}

// ── Supabase insert helper ───────────────────────────────────────────────
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
    headers: {
      "Content-Type": "application/json",
      "apikey": key,
      "Authorization": `Bearer ${key}`,
      "Prefer": "return=minimal",
    },
    body: JSON.stringify(row),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    console.log(
      `[SUPABASE_FALLBACK_INSERT_ERROR] ${JSON.stringify({ requestId, status: res.status, detail: errText, payload: row })}`
    );
  }
  return res;
}

export default app;