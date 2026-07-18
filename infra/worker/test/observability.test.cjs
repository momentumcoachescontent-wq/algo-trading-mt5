const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildSignalObservability,
  normalizeDecision,
  normalizeExecutionScope,
  normalizeSignalReasons,
  normalizeTradeIdentity,
  resolveSignalEvalId,
} = require("../.tmp-test/observability.js");
const {
  chooseOpenTradeCandidate,
} = require("../.tmp-test/tradeCandidate.js");

test("valid shadow entry is not labeled ERROR", () => {
  const payload = {
    symbol: "USDJPY",
    ea_version: "v4.43.1",
    phase: "Stage10C-D1ContextIntegrity",
    eval_time: "2026-07-15T12:00:00Z",
    bar_time_h4: "2026-07-15T08:00:00Z",
    direction: "buy",
    entry_price: 162.299,
    action: "ENTRY_ACCEPTED",
    decision: "ERROR",
    would_have_traded: true,
    execution_scope: {
      mode: "SHADOW_ONLY",
      order_send_allowed: false,
      shadow_only: true,
      reason: "EA_REAL_TRADING_DISABLED_SAFE_FALLBACK",
    },
  };

  const result = buildSignalObservability(payload);
  assert.equal(result.decision, "ENTRY_READY_SHADOW_ONLY_BLOCKED");
  assert.equal(result.technicalSignalStatus, "ENTRY_READY");
  assert.equal(result.executionMode, "SHADOW_ONLY");
  assert.equal(result.orderSendAllowed, false);
  assert.equal(result.barH4, "2026-07-15T08:00:00Z");
  assert.equal(
    result.reasons.executionDeniedReason,
    "EA_REAL_TRADING_DISABLED_SAFE_FALLBACK",
  );
});

test("valid real entry is labeled real allowed", () => {
  const payload = {
    action: "ENTRY_ACCEPTED",
    signal_status: "ENTRY_READY",
    execution_scope: { mode: "REAL", order_send_allowed: true },
  };
  assert.equal(normalizeDecision(payload), "ENTRY_READY_REAL_ALLOWED");
});

test("technical and governance reasons are separated", () => {
  const technical = normalizeSignalReasons({ block_reason: "body_c1_fail" });
  assert.equal(technical.primarySignalReason, "body_c1_fail");
  assert.equal(technical.governanceGuardReason, null);

  const governance = normalizeSignalReasons({
    block_reason: "friday_no_new_entry_window",
  });
  assert.equal(governance.primarySignalReason, null);
  assert.equal(governance.governanceGuardReason, "friday_no_new_entry_window");
});

test("scope reason is not mixed with signal reason", () => {
  const reasons = normalizeSignalReasons({
    action: "SCOPE_DENY",
    primary_signal_reason: "valid_buy_setup",
    execution_scope: {
      mode: "SHADOW_ONLY",
      order_send_allowed: false,
      reason: "SHADOW_POLICY",
    },
  });
  assert.equal(reasons.primarySignalReason, "valid_buy_setup");
  assert.equal(reasons.executionDeniedReason, "SHADOW_POLICY");
});

test("nested execution scope JSON string is accepted", () => {
  const scope = normalizeExecutionScope({
    execution_scope: JSON.stringify({
      mode: "SHADOW_ONLY",
      order_send_allowed: false,
      policy_name: "stage10c",
    }),
  });
  assert.equal(scope.mode, "SHADOW_ONLY");
  assert.equal(scope.orderSendAllowed, false);
  assert.equal(scope.policyName, "stage10c");
});

test("signal_eval_id uses the canonical transparent contract", () => {
  const payload = {
    symbol: "usdjpy",
    ea_version: "V4.43.1",
    phase: "Stage10C-D1ContextIntegrity",
    eval_time: "2026-07-15T12:00:00.000Z",
    direction: "BUY",
    entry_price: "162.29900000",
  };
  assert.equal(
    resolveSignalEvalId(payload),
    "stage10c-sig-v1|USDJPY|v4.43.1|stage10c-d1contextintegrity|2026-07-15T12:00:00Z|buy|162.299",
  );
});

test("signal_eval_id is deterministic and retry-safe", () => {
  const payload = {
    symbol: "USDJPY",
    ea_version: "v4.43.1",
    phase: "Stage10C-D1ContextIntegrity",
    eval_time: "2026-07-15T12:00:00Z",
    direction: "buy",
    entry_price: 162.299,
  };
  assert.equal(resolveSignalEvalId(payload), resolveSignalEvalId({ ...payload }));
  assert.match(resolveSignalEvalId(payload), /^stage10c-sig-v1\|/);
});

test("provided signal_eval_id is preserved", () => {
  assert.equal(resolveSignalEvalId({ signal_eval_id: "sig-explicit" }), "sig-explicit");
});

test("trade open keeps explicit order ticket separate from position id", () => {
  const identity = normalizeTradeIdentity(
    {
      ticket: 152340804622,
      order_ticket: 2016949262,
      position_id: 152340804622,
      signal_eval_id: "sig-1",
      execution_scope: { mode: "REAL" },
    },
    "trade_open",
  );
  assert.equal(identity.ticket, 152340804622);
  assert.equal(identity.orderTicket, 2016949262);
  assert.equal(identity.dealTicket, null);
  assert.equal(identity.positionId, 152340804622);
  assert.equal(identity.linkStatus, "LINKED_SIGNAL_ORDER_POSITION");
});

test("actual v4430 open ticket is treated as position, not invented order", () => {
  const payload = {
    event: "trade_open",
    symbol: "USDJPY",
    ticket: 152340804622,
    position_id: 152340804622,
    direction: "buy",
    entry_price: 162.299,
    open_price: 162.299,
    open_time: "2026-07-15T12:00:00Z",
    ea_version: "v4.43.0",
    phase: "Stage10C-USDJPYFirstGovernanceReset",
    execution_mode: "REAL",
  };
  const identity = normalizeTradeIdentity(payload, "trade_open");
  assert.equal(identity.ticket, 152340804622);
  assert.equal(identity.positionId, 152340804622);
  assert.equal(identity.orderTicket, null);
  assert.match(identity.signalEvalId, /^stage10c-sig-v1\|/);
  assert.equal(identity.linkStatus, "LINKED_SIGNAL_POSITION_MISSING_ORDER_TICKET");
});

test("signal and trade payloads derive the same correlation id", () => {
  const common = {
    symbol: "USDJPY",
    ea_version: "v4.43.0",
    phase: "Stage10C-USDJPYFirstGovernanceReset",
    direction: "buy",
    entry_price: 162.299,
  };
  const signalId = resolveSignalEvalId({
    ...common,
    eval_time: "2026-07-15T12:00:00.000Z",
    bar_time_h4: "2026-07-15T08:00:00Z",
  });
  const trade = normalizeTradeIdentity(
    {
      ...common,
      open_time: "2026-07-15T12:00:00Z",
      ticket: 152340804622,
      position_id: 152340804622,
    },
    "trade_open",
  );
  assert.equal(trade.signalEvalId, signalId);
});

test("trade close keeps explicit deal ticket separate from position id", () => {
  const identity = normalizeTradeIdentity(
    {
      ticket: 152340804622,
      deal_ticket: 301,
      position_id: 152340804622,
    },
    "trade_close",
  );
  assert.equal(identity.ticket, 152340804622);
  assert.equal(identity.orderTicket, null);
  assert.equal(identity.dealTicket, 301);
  assert.equal(identity.positionId, 152340804622);
  assert.equal(identity.linkStatus, "CLOSE_POSITION_AND_DEAL_IDENTIFIED");
});

test("legacy open ticket is never copied into position_id", () => {
  const identity = normalizeTradeIdentity({ ticket: 123 }, "trade_open");
  assert.equal(identity.orderTicket, 123);
  assert.equal(identity.positionId, null);
  assert.equal(identity.linkStatus, "LEGACY_OPEN_IDENTITY_INCOMPLETE");
});

test("single candidate with explicit mode mismatch is rejected", () => {
  const candidate = chooseOpenTradeCandidate(
    [{ id: 1, execution_mode: "REAL", strategy_variant: "control" }],
    "SHADOW_ONLY",
    "control",
  );
  assert.equal(candidate, null);
});

test("single candidate with explicit variant mismatch is rejected", () => {
  const candidate = chooseOpenTradeCandidate(
    [{ id: 1, execution_mode: "REAL", strategy_variant: "control" }],
    "REAL",
    "challenger",
  );
  assert.equal(candidate, null);
});

test("single legacy candidate with missing metadata is accepted", () => {
  const candidate = chooseOpenTradeCandidate(
    [{ id: 1, execution_mode: null, strategy_variant: null }],
    "REAL",
    "control",
  );
  assert.equal(candidate.id, 1);
});

test("normalization never authorizes an order", () => {
  const result = buildSignalObservability({
    action: "ENTRY_ACCEPTED",
    execution_scope: { mode: "SHADOW_ONLY", order_send_allowed: false },
  });
  assert.equal(result.orderSendAllowed, false);
  assert.equal(result.decision, "ENTRY_READY_SHADOW_ONLY_BLOCKED");
});
