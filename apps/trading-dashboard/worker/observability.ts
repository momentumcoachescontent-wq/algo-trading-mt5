/* Observational endpoints only: no order, risk, or EA mutation. */
type Env = {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
};
type Row = Record<string, unknown>;
type ApiResult = { rows: Row[]; error?: string; status?: number };
const json = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify(data), {
    status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
const isObject = (v: unknown): v is Row => Boolean(v) && typeof v === "object" && !Array.isArray(v);
function payload(v: unknown): Row {
  if (isObject(v)) return v;
  if (typeof v !== "string") return {};
  try { const data: unknown = JSON.parse(v); return isObject(data) ? data : {}; }
  catch { return {}; }
}
const text = (v: unknown) => typeof v === "string" ? v : "";
const numeric = (v: unknown): number | null =>
  v === null || v === undefined || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null;
const instant = (v: unknown): number => {
  const t = Date.parse(text(v));
  return Number.isFinite(t) ? t : 0;
};
function timeframe(r: Row): string {
  const raw = payload(r.raw_payload);
  const value = text(raw.timeframe || r.timeframe).toUpperCase();
  return value === "D1" || value === "H4" ? value : r.bar_h4 != null ? "H4" : "UNKNOWN";
}
function isMatch(r: Row, tf: string): boolean { return tf === "ALL" || timeframe(r) === tf; }
function deduplicateSignals(rows: Row[]): Row[] {
  const seen = new Set<string>();
  return rows.filter(r => {
    const raw = payload(r.raw_payload);
    const key = [r.symbol, r.ea_version, r.strategy_variant, timeframe(r),
      raw.signal_eval_id ?? r.bar_h4 ?? raw.bar_time ?? r.eval_time ?? r.created_at].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
const decision = (r: Row): string => {
  const state = text(r.decision).toUpperCase();
  const action = text(r.action).toUpperCase();
  // Shadow-only entry-ready rows may contain BOTH ENTRY_READY and BLOCKED.
  // A retained block_reason must not override an accepted entry decision.
  if (state.includes("ENTRY_READY") || action.startsWith("ENTRY_READY") || action === "ENTRY_ACCEPTED") return "ENTRY_READY";
  if (state.includes("ERROR") || action.includes("ERROR")) return "ERROR";
  if (state.includes("BLOCKED") || action.includes("BLOCKED") || r.block_reason != null) return "BLOCKED";
  return state || action || "UNKNOWN";
};
async function select(env: Env, table: string, columns: string, filters: Record<string, string>, limit: number): Promise<ApiResult> {
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY)
    return { rows: [], error: "Missing restricted dashboard Supabase credentials", status: 503 };
  const params = new URLSearchParams();
  params.set("select", columns);
  for (const [k, v] of Object.entries(filters)) params.set(k, v);
  params.set("order", table === "observability_candles" ? "bar_time.desc" : "created_at.desc");
  params.set("limit", String(limit));
  try {
    const r = await fetch(env.SUPABASE_URL + "/rest/v1/" + table + "?" + params, {
      headers: {
        apikey: env.SUPABASE_SERVICE_ROLE_KEY,
        authorization: "Bearer " + env.SUPABASE_SERVICE_ROLE_KEY,
        "accept-profile": "public",
      },
    });
    if (!r.ok) return { rows: [], error: "Supabase query failed (" + r.status + ")", status: 502 };
    const rows: unknown = await r.json();
    if (!Array.isArray(rows)) return { rows: [], error: "Unexpected query payload", status: 502 };
    return { rows: rows.filter(isObject) };
  } catch {
    return { rows: [], error: "Observability data source unreachable", status: 502 };
  }
}
function validate(url: URL): { symbol: string; version: string; tf: string; limit: number } | null {
  const symbol = (url.searchParams.get("symbol") ?? "USDJPY").toUpperCase();
  const version = url.searchParams.get("version") ?? "";
  const tf = (url.searchParams.get("timeframe") ?? "ALL").toUpperCase();
  const limit = Number(url.searchParams.get("limit") ?? "250");
  if (!/^[A-Z0-9._-]{2,24}$/.test(symbol) ||
      (version !== "" && !/^[A-Za-z0-9._-]{2,48}$/.test(version)) ||
      !["ALL", "H4", "D1"].includes(tf) ||
      !Number.isInteger(limit) || limit < 1 || limit > 1000) return null;
  return { symbol, version, tf, limit };
}
function versionFilter(version: string): Record<string, string> {
  return version ? { ea_version: "eq." + version } : {};
}
function tradeClosed(r: Row) { return r.close_time != null || text(r.event_type).toLowerCase() === "close"; }
function tradeView(r: Row) {
  const raw = payload(r.raw_payload);
  return {
    symbol: r.symbol, ea_version: r.ea_version, timeframe: timeframe(r),
    direction: r.direction, event_type: r.event_type, open_time: r.open_time,
    close_time: r.close_time, open_price: numeric(r.open_price), close_price: numeric(r.close_price),
    pnl: numeric(r.pnl), position_id: r.position_id, ticket: r.ticket,
    strategy_variant: r.strategy_variant, sleeve: raw.sleeve ?? null,
    excluded: r.exclude_from_edge === true,
  };
}
function signalView(r: Row) {
  const raw = payload(r.raw_payload);
  return {
    kind: "signal", symbol: r.symbol, ea_version: r.ea_version, strategy_variant: r.strategy_variant,
    timeframe: timeframe(r), at: r.eval_time ?? r.created_at,
    // Time of the already-closed bar the EA examined, not the next-tick evaluation time.
    bar_time: text(raw.bar_time) || text(r.bar_h4) || null,
    created_at: r.created_at, decision: decision(r),
    reason: r.block_reason ?? raw.reason_code ?? raw.order_message ?? null,
    direction: r.direction, close: numeric(raw.close),
    ema: numeric(raw.ema21 ?? raw.ema),
    sma: numeric(raw.sma), channel_high: numeric(raw.channel_high),
    channel_low: numeric(raw.channel_low), atr: numeric(r.atr_h4),
    distance_to_ema_atr: numeric(r.distance_to_ema_atr),
    session: r.session ?? null, trend: r.trend_state ?? null,
    order_status: raw.order_status ?? null,
  };
}
async function assets(env: Env): Promise<Response> {
  const [signals, trades] = await Promise.all([
    select(env, "signal_evals", "symbol,ea_version,strategy_variant,created_at,bar_h4,raw_payload", {}, 2500),
    select(env, "trades", "symbol,ea_version,strategy_variant,created_at,raw_payload", {}, 500),
  ]);
  if (signals.error) return json({ ok: false, error: signals.error }, signals.status);
  if (trades.error) return json({ ok: false, error: trades.error }, trades.status);
  const groups = new Map<string, { symbol: string; version: string; timeframe: string; strategy: string; last_seen: string }>();
  for (const r of [...signals.rows, ...trades.rows]) {
    const symbol = text(r.symbol), version = text(r.ea_version);
    if (!symbol || !version) continue;
    const tf = timeframe(r), strategy = text(r.strategy_variant);
    const k = [symbol, version, tf, strategy].join("|");
    const last_seen = text(r.created_at);
    const old = groups.get(k);
    if (!old || instant(last_seen) > instant(old.last_seen)) groups.set(k, { symbol, version, timeframe: tf, strategy, last_seen });
  }
  return json({ ok: true, generated_at: new Date().toISOString(),
    scope: "most recent 2500 signal rows and 500 trade rows",
    assets: [...groups.values()].sort((a,b) => instant(b.last_seen) - instant(a.last_seen)) });
}
async function timeline(env: Env, args: NonNullable<ReturnType<typeof validate>>): Promise<Response> {
  const filters = { symbol: "eq." + args.symbol, ...versionFilter(args.version) };
  const [s, t] = await Promise.all([
    select(env, "signal_evals", "created_at,symbol,ea_version,strategy_variant,raw_payload,bar_h4,eval_time,decision,action,block_reason,direction,atr_h4,distance_to_ema_atr,session,trend_state", filters, 1000),
    select(env, "trades", "created_at,symbol,ea_version,strategy_variant,raw_payload,event_type,open_time,close_time,open_price,close_price,pnl,position_id,ticket,direction,exclude_from_edge", filters, 1000),
  ]);
  if (s.error || t.error) return json({ ok: false, error: s.error || t.error }, s.status || t.status);
  const signals = deduplicateSignals(s.rows.filter(r => isMatch(r, args.tf)));
  const trades = t.rows.filter(r => isMatch(r, args.tf)).map(tradeView);
  const evaluations = signals.map(signalView).sort((a,b)=>instant(text(b.at))-instant(text(a.at))).slice(0,args.limit);
  return json({ ok: true, generated_at: new Date().toISOString(),
    scope: {symbol: args.symbol,version:args.version || "ALL",timeframe:args.tf, signals_scanned:s.rows.length, trades_scanned:t.rows.length, sampled:true},
    evaluations, trades: trades.slice(0,args.limit) });
}
async function summary(env: Env, args: NonNullable<ReturnType<typeof validate>>): Promise<Response> {
  const filters = { symbol: "eq." + args.symbol, ...versionFilter(args.version) };
  const [s,t,e] = await Promise.all([
    select(env,"signal_evals","created_at,symbol,ea_version,strategy_variant,raw_payload,bar_h4,eval_time,decision,action,block_reason",filters,1000),
    select(env,"trades","created_at,symbol,ea_version,strategy_variant,raw_payload,close_time,event_type,pnl,exclude_from_edge",filters,1000),
    select(env,"ea_events","created_at,symbol,ea_version,event,boot_id",filters,1000),
  ]);
  if (s.error || t.error || e.error) return json({ok:false,error:s.error||t.error||e.error},s.status||t.status||e.status);
  const signals = deduplicateSignals(s.rows.filter(r=>isMatch(r,args.tf)));
  const closed = t.rows.filter(r=>isMatch(r,args.tf) && tradeClosed(r) && r.exclude_from_edge!==true);
  const pnl = closed.map(r=>numeric(r.pnl)).filter((x):x is number=>x!==null);
  const reasons: Record<string,number> = {};
  for (const r of signals) {
    const d = decision(r);
    if (d!=="BLOCKED") continue;
    const reason = text(r.block_reason) || text(payload(r.raw_payload).reason_code) || "UNSPECIFIED";
    reasons[reason] = (reasons[reason]||0)+1;
  }
  const latestEval = signals.reduce((x,r)=>Math.max(x,instant(r.created_at)),0);
  const latestLifecycle = e.rows.reduce((x,r)=>Math.max(x,instant(r.created_at)),0);
  const boots = new Set(e.rows.map(r=>text(r.boot_id)).filter(Boolean));
  const ageMinutes = latestEval ? Math.floor((Date.now()-latestEval)/60000):null;
  const grossProfit = pnl.filter(x=>x>0).reduce((a,b)=>a+b,0);
  const grossLoss = -pnl.filter(x=>x<0).reduce((a,b)=>a+b,0);
  return json({ok:true,generated_at:new Date().toISOString(),symbol:args.symbol,version:args.version||"ALL",timeframe:args.tf,
    sample:{signal_rows:s.rows.length,trade_rows:t.rows.length,lifecycle_rows:e.rows.length,limited:s.rows.length===1000||t.rows.length===1000||e.rows.length===1000},
    evaluations:signals.length,blocked:signals.filter(r=>decision(r)==="BLOCKED").length,
    entry_ready:signals.filter(r=>decision(r)==="ENTRY_READY").length,
    errors:signals.filter(r=>decision(r)==="ERROR").length,
    last_evaluation:latestEval?new Date(latestEval).toISOString():null,
    evaluation_age_minutes:ageMinutes,
    last_lifecycle_event:latestLifecycle?new Date(latestLifecycle).toISOString():null,
    recent_lifecycle_events:e.rows.length,distinct_boot_ids:boots.size,
    lifecycle_note:"Lifecycle events are not proof of connectivity or fresh H4/D1 evaluations",
    last_decision:signals.length?decision(signals[0]):null,
    blocked_reasons:Object.entries(reasons).map(([reason,count])=>({reason,count})).sort((a,b)=>b.count-a.count).slice(0,12),
    closed_trades:pnl.length,realized_pnl:pnl.reduce((a,b)=>a+b,0),
    win_rate:pnl.length?pnl.filter(x=>x>0).length/pnl.length:null,
    profit_factor:grossLoss>0?grossProfit/grossLoss:null,
    economic_scope:"sample-only: not a complete audited lifetime ledger" });
}
async function candles(env:Env,args:NonNullable<ReturnType<typeof validate>>):Promise<Response> {
  if(args.tf==="ALL")return json({ok:false,error:"Select H4 or D1 for candles"},400);
  const d=await select(env,"observability_candles",
    "symbol,timeframe,bar_time,open,high,low,close,tick_volume,source",
    {symbol:"eq."+args.symbol,timeframe:"eq."+args.tf},Math.min(args.limit,1000));
  if(d.error)return json({ok:false,error:d.error},d.status);
  const rows=d.rows.sort((a,b)=>instant(a.bar_time)-instant(b.bar_time)).map(r=>({
    time:r.bar_time,open:r.open,high:r.high,low:r.low,close:r.close,volume:r.tick_volume
  }));
  return json({ok:true,symbol:args.symbol,timeframe:args.tf,source:"MT5_PASSIVE_OHLC",
    last_candle:rows.length?rows[rows.length-1].time:null,rows});
}
export async function observabilityRequest(request:Request, env:Env):Promise<Response|null> {
  const url=new URL(request.url);
  if(!url.pathname.startsWith("/api/observability/"))return null;
  if(request.method!=="GET")return json({ok:false,error:"read-only endpoint"},405);
  if(url.pathname==="/api/observability/assets")return assets(env);
  const args=validate(url);
  if(!args)return json({ok:false,error:"Invalid symbol, version, timeframe or limit"},400);
  if(url.pathname==="/api/observability/summary")return summary(env,args);
  if(url.pathname==="/api/observability/timeline")return timeline(env,args);
  if(url.pathname==="/api/observability/candles")return candles(env,args);
  return json({ok:false,error:"Unknown observability route"},404);
}
