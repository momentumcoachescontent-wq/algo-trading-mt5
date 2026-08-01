const test = require("node:test");
const assert = require("node:assert/strict");

const app = require("../.tmp-test/index.js").default;

const env = {
  SUPABASE_URL: "https://example.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "test-key",
  EA_WEBHOOK_SECRET: "test-secret",
};

function lifecycleRequest(payload) {
  return app.request(
    "http://worker/trading/webhook",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-EA-Secret": "test-secret",
      },
      body: JSON.stringify(payload),
    },
    env,
  );
}

test("lifecycle handler persists enriched ea_init row", { concurrency: false }, async (t) => {
  const originalFetch = global.fetch;
  t.after(() => {
    global.fetch = originalFetch;
  });

  let persistedRow;
  global.fetch = async (_url, init) => {
    persistedRow = JSON.parse(init.body);
    return new Response(null, { status: 201 });
  };

  const response = await lifecycleRequest({
    event: "ea_init",
    symbol: "USDJPY",
    ea_version: "v4.43.1",
    phase: "Stage10C-D1ContextIntegrity",
    execution_mode: "SHADOW_ONLY",
    capital_enabled: false,
    order_send_allowed: false,
  });
  const responseBody = await response.json();

  assert.equal(response.status, 200);
  assert.equal(persistedRow.request_id, responseBody.requestId);
  assert.equal(persistedRow.execution_mode, "SHADOW_ONLY");
  assert.equal(persistedRow.execution_scope.capital_enabled, false);
  assert.equal(persistedRow.execution_scope.order_send_allowed, false);
  assert.equal(
    persistedRow.raw_payload.worker_request_id,
    responseBody.requestId,
  );
});

test("lifecycle Supabase rejection returns HTTP 500", { concurrency: false }, async (t) => {
  const originalFetch = global.fetch;
  t.after(() => {
    global.fetch = originalFetch;
  });

  global.fetch = async () => new Response("rejected", { status: 400 });

  const response = await lifecycleRequest({
    event: "ea_init",
    symbol: "USDJPY",
    ea_version: "v4.43.1",
    phase: "Stage10C-D1ContextIntegrity",
    execution_mode: "SHADOW_ONLY",
    capital_enabled: false,
    order_send_allowed: false,
  });
  const responseBody = await response.json();

  assert.equal(response.status, 500);
  assert.match(responseBody.error, /Supabase ea_events insert failed: 400/);
});
