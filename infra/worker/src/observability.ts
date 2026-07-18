export type Payload = Record<string, unknown>;
export type TradeEvent = "trade_open" | "trade_close";

export interface NormalizedExecutionScope {
  mode: string | null;
  orderSendAllowed: boolean | null;
  capitalEnabled: boolean | null;
  shadowOnly: boolean | null;
  policyName: string | null;
  reason: string | null;
}

export interface NormalizedReasons {
  primarySignalReason: string | null;
  governanceGuardReason: string | null;
  executionDeniedReason: string | null;
}

export interface SignalObservability {
  signalEvalId: string;
  decision: string;
  technicalSignalStatus: string;
  executionMode: string | null;
  orderSendAllowed: boolean | null;
  wouldHaveTraded: boolean;
  policyName: string | null;
  strategyVariant: string | null;
  guardVersion: string | null;
  magicNumber: number | null;
  bootId: string | null;
  barH4: string | null;
  reasons: NormalizedReasons;
}

export interface TradeIdentity {
  ticket: string | number | null;
  orderTicket: string | number | null;
  dealTicket: string | number | null;
  positionId: string | number | null;
  signalEvalId: string | null;
  executionMode: string | null;
  strategyVariant: string | null;
  guardVersion: string | null;
  magicNumber: number | null;
  bootId: string | null;
  linkStatus: string;
}

const GOVERNANCE_REASON_MARKERS = [
  "position_open",
  "session_not_allowed",
  "friday_no_new_entry",
  "circuit_break",
  "daily_dd",
  "weekly_pause",
  "governance",
  "symbol_not_allowed",
  "max_positions",
  "spread_guard",
];

function isRecord(value: unknown): value is Payload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseRecord(value: unknown): Payload {
  if (isRecord(value)) return value;
  if (typeof value !== "string") return {};
  const trimmed = value.trim();
  if (!trimmed.startsWith("{")) return {};
  try {
    const parsed = JSON.parse(trimmed);
    return isRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function firstDefined(...values: unknown[]): unknown {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

export function toText(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  return String(value).trim() || null;
}

export function toNumber(value: unknown): number | null {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function toBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1") return true;
  if (value === 0 || value === "0") return false;
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  if (["true", "yes", "y", "on"].includes(normalized)) return true;
  if (["false", "no", "n", "off"].includes(normalized)) return false;
  return null;
}

function normalizeUpper(value: unknown): string {
  return toText(value)?.toUpperCase() ?? "";
}

function meaningfulReason(...values: unknown[]): string | null {
  for (const value of values) {
    const text = toText(value);
    if (text && !["ok", "none", "n/a"].includes(text.toLowerCase())) return text;
  }
  return null;
}

function isGovernanceReason(reason: string | null): boolean {
  if (!reason) return false;
  const normalized = reason.toLowerCase();
  return GOVERNANCE_REASON_MARKERS.some((marker) => normalized.includes(marker));
}

export function normalizeExecutionScope(body: Payload): NormalizedExecutionScope {
  const scope = parseRecord(body.execution_scope);
  const mode = toText(firstDefined(scope.mode, body.execution_mode, body.mode));
  const orderSendAllowed = toBoolean(
    firstDefined(scope.order_send_allowed, body.order_send_allowed),
  );
  return {
    mode,
    orderSendAllowed,
    capitalEnabled: toBoolean(firstDefined(scope.capital_enabled, body.capital_enabled)),
    shadowOnly: toBoolean(firstDefined(scope.shadow_only, body.shadow_only)),
    policyName: toText(firstDefined(scope.policy_name, body.policy_name)),
    reason: meaningfulReason(
      scope.reason,
      body.execution_denied_reason,
      body.scope_reason,
      body.final_scope_reason,
      body.reason_code,
    ),
  };
}

function hasEntryReadyEvidence(body: Payload): boolean {
  const markers = [
    normalizeUpper(body.technical_signal_status),
    normalizeUpper(body.signal_status),
    normalizeUpper(body.action),
    normalizeUpper(body.decision),
  ];
  return (
    toBoolean(body.would_have_traded) === true ||
    markers.some((marker) => marker.includes("ENTRY_READY") || marker.includes("ENTRY_ACCEPTED"))
  );
}

function hasScopeDeniedEvidence(body: Payload, scope: NormalizedExecutionScope): boolean {
  const markers = [
    normalizeUpper(body.action),
    normalizeUpper(body.decision),
    normalizeUpper(body.guard),
  ];
  return (
    markers.some(
      (marker) =>
        marker.includes("SCOPE_DENY") ||
        marker.includes("FINAL_SCOPE_GUARD") ||
        marker.includes("BLOCKED_BY_EXECUTION_SCOPE"),
    ) ||
    (hasEntryReadyEvidence(body) && scope.orderSendAllowed === false)
  );
}

export function normalizeTechnicalSignalStatus(body: Payload): string {
  const explicit = toText(
    firstDefined(body.technical_signal_status, body.signal_status),
  );
  if (explicit) return explicit.toUpperCase();
  if (hasEntryReadyEvidence(body)) return "ENTRY_READY";
  if (meaningfulReason(body.block_reason, body.signal_block_reason, body.fail_reason)) {
    return "BLOCKED";
  }
  const h4Signal = toNumber(
    firstDefined(body.filtered_h4_signal, body.h4_signal, body.signal_h4),
  );
  if (h4Signal !== null && h4Signal !== 0) return "RAW_SIGNAL";
  return "NO_SIGNAL";
}

export function normalizeDecision(body: Payload): string {
  const scope = normalizeExecutionScope(body);
  const entryReady = hasEntryReadyEvidence(body);
  const scopeDenied = hasScopeDeniedEvidence(body, scope);
  const blockReason = meaningfulReason(
    body.block_reason,
    body.signal_block_reason,
    body.fail_reason,
  );

  // Entry evidence has precedence over a legacy/raw decision=ERROR label.
  if (entryReady) {
    if (
      normalizeUpper(scope.mode) === "SHADOW_ONLY" ||
      scope.shadowOnly === true ||
      scope.orderSendAllowed === false
    ) {
      return "ENTRY_READY_SHADOW_ONLY_BLOCKED";
    }
    if (scope.orderSendAllowed === true) return "ENTRY_READY_REAL_ALLOWED";
    return "ENTRY_READY";
  }

  if (scopeDenied) return "BLOCKED_BY_EXECUTION_SCOPE";
  if (blockReason) {
    return isGovernanceReason(blockReason)
      ? "BLOCKED_BY_GOVERNANCE_GUARD"
      : "BLOCKED_BY_TECHNICAL_GUARD";
  }

  const rawDecision = normalizeUpper(body.decision);
  const explicitError = firstDefined(body.error, body.error_reason);
  if (rawDecision === "ERROR" || explicitError) return "ERROR";
  return normalizeTechnicalSignalStatus(body) === "RAW_SIGNAL" ? "RAW_SIGNAL" : "NO_SIGNAL";
}

export function normalizeSignalReasons(body: Payload): NormalizedReasons {
  const scope = normalizeExecutionScope(body);
  const blockReason = meaningfulReason(
    body.block_reason,
    body.signal_block_reason,
    body.fail_reason,
  );
  const generalReason = meaningfulReason(body.reason);
  const decision = normalizeDecision(body);

  let primarySignalReason = meaningfulReason(
    body.primary_signal_reason,
    body.signal_reason,
    body.entry_quality_guard_reason,
    body.integrity_guard_reason,
  );
  let governanceGuardReason = meaningfulReason(
    body.governance_guard_reason,
    body.guard_reason,
    body.execution_guard_reason,
    body.gov_reason,
  );
  let executionDeniedReason = meaningfulReason(
    body.execution_denied_reason,
    scope.reason,
    body.scope_reason,
    body.final_scope_reason,
  );

  if (blockReason) {
    if (isGovernanceReason(blockReason)) {
      governanceGuardReason ??= blockReason;
    } else {
      primarySignalReason ??= blockReason;
    }
  }

  if (generalReason) {
    if (decision.includes("EXECUTION_SCOPE") || decision.includes("SHADOW_ONLY")) {
      executionDeniedReason ??= generalReason;
    } else if (isGovernanceReason(generalReason)) {
      governanceGuardReason ??= generalReason;
    } else {
      primarySignalReason ??= generalReason;
    }
  }

  return {
    primarySignalReason,
    governanceGuardReason,
    executionDeniedReason,
  };
}

function fnv1a64(value: string): string {
  let hash = 0xcbf29ce484222325n;
  const prime = 0x100000001b3n;
  for (const byte of new TextEncoder().encode(value)) {
    hash ^= BigInt(byte);
    hash = BigInt.asUintN(64, hash * prime);
  }
  return hash.toString(16).padStart(16, "0");
}

function correlationTime(body: Payload): string | null {
  // eval_time and trade open_time are the same instant in the current Stage10C
  // payloads; prioritizing them enables deterministic signal-position linking.
  return toText(
    firstDefined(
      body.eval_time,
      body.open_time,
      body.entry_time,
      body.event_time,
      body.timestamp,
      body.bar_h4,
      body.bar_time_h4,
      body.bar_time,
      body.eval_bar_time,
    ),
  );
}

function hasCorrelationMaterial(body: Payload): boolean {
  return Boolean(
    toText(body.symbol) &&
      toText(body.ea_version) &&
      correlationTime(body) &&
      toText(firstDefined(body.direction, body.signal_direction, body.order_direction)) &&
      toText(firstDefined(body.entry_price, body.open_price, body.price)),
  );
}

export function resolveSignalEvalId(body: Payload): string {
  const provided = toText(firstDefined(body.signal_eval_id, body.signal_id));
  if (provided) return provided;

  const canonical = [
    toText(body.symbol) ?? "unknown-symbol",
    toText(body.ea_version) ?? "unknown-version",
    toText(firstDefined(body.strategy_variant, body.phase)) ?? "unknown-variant",
    correlationTime(body) ?? "unknown-time",
    toText(firstDefined(body.direction, body.signal_direction, body.order_direction, body.action)) ??
      "no-direction",
    toText(firstDefined(body.entry_price, body.open_price, body.price)) ?? "no-entry",
  ].join("|");
  return `stage10c-sig-${fnv1a64(canonical)}`;
}

export function buildSignalObservability(body: Payload): SignalObservability {
  const scope = normalizeExecutionScope(body);
  return {
    signalEvalId: resolveSignalEvalId(body),
    decision: normalizeDecision(body),
    technicalSignalStatus: normalizeTechnicalSignalStatus(body),
    executionMode: scope.mode,
    orderSendAllowed: scope.orderSendAllowed,
    wouldHaveTraded: toBoolean(body.would_have_traded) ?? false,
    policyName: scope.policyName,
    strategyVariant: toText(firstDefined(body.strategy_variant, body.phase)),
    guardVersion: toText(body.guard_version),
    magicNumber: toNumber(firstDefined(body.magic_number, body.magic)),
    bootId: toText(body.boot_id),
    barH4: toText(
      firstDefined(body.bar_h4, body.bar_time_h4, body.bar_time, body.eval_bar_time),
    ),
    reasons: normalizeSignalReasons(body),
  };
}

export function normalizeTradeIdentity(body: Payload, event: TradeEvent): TradeIdentity {
  const scope = normalizeExecutionScope(body);
  const legacyTicket = firstDefined(body.ticket) as string | number | null;
  const positionId = firstDefined(body.position_id, body.position_ticket) as
    | string
    | number
    | null;
  const ticketRole = normalizeUpper(body.ticket_role);

  // The current v4.43.0 trade_open payload sends ticket == position_id. Never
  // infer an order ticket from that legacy field unless the payload explicitly
  // declares ticket_role=ORDER or has no position identity at all.
  const orderTicket = firstDefined(
    body.order_ticket,
    body.order_id,
    event === "trade_open" && ticketRole === "ORDER" ? legacyTicket : null,
    event === "trade_open" && !positionId ? legacyTicket : null,
  ) as string | number | null;
  const dealTicket = firstDefined(
    body.deal_ticket,
    body.deal_id,
    event === "trade_close" && ticketRole === "DEAL" ? legacyTicket : null,
    event === "trade_close" && !positionId ? legacyTicket : null,
  ) as string | number | null;

  const explicitSignalEvalId = toText(firstDefined(body.signal_eval_id, body.signal_id));
  const signalEvalId = explicitSignalEvalId ??
    (hasCorrelationMaterial(body) ? resolveSignalEvalId(body) : null);

  let linkStatus: string;
  if (event === "trade_open") {
    if (positionId && signalEvalId && orderTicket) {
      linkStatus = "LINKED_SIGNAL_ORDER_POSITION";
    } else if (positionId && signalEvalId) {
      linkStatus = "LINKED_SIGNAL_POSITION_MISSING_ORDER_TICKET";
    } else if (positionId && orderTicket) {
      linkStatus = "LINKED_ORDER_POSITION_MISSING_SIGNAL";
    } else if (positionId) {
      linkStatus = "POSITION_ONLY_NO_SIGNAL_OR_ORDER_LINK";
    } else if (signalEvalId) {
      linkStatus = "SIGNAL_LINK_MISSING_POSITION_ID";
    } else {
      linkStatus = "LEGACY_OPEN_IDENTITY_INCOMPLETE";
    }
  } else if (positionId && dealTicket) {
    linkStatus = "CLOSE_POSITION_AND_DEAL_IDENTIFIED";
  } else if (positionId) {
    linkStatus = "CLOSE_POSITION_IDENTIFIED_MISSING_DEAL_TICKET";
  } else {
    linkStatus = "UNMATCHED_CLOSE_IDENTITY";
  }

  return {
    ticket: legacyTicket,
    orderTicket,
    dealTicket,
    positionId,
    signalEvalId,
    executionMode: scope.mode,
    strategyVariant: toText(firstDefined(body.strategy_variant, body.phase)),
    guardVersion: toText(body.guard_version),
    magicNumber: toNumber(firstDefined(body.magic_number, body.magic)),
    bootId: toText(body.boot_id),
    linkStatus,
  };
}
