#!/usr/bin/env node
// BNB Data Engine — freshness monitor for BNB Chain RPC endpoints.
// Polls endpoints, measures block age, reports freshness status as JSON.

const ENDPOINTS = (process.env.BNB_RPC_ENDPOINTS ??
  "https://bsc-rpc.publicnode.com,https://1rpc.io/bnb"
).split(",").map((s) => s.trim()).filter(Boolean);

const FRESH_LIMIT_S = Number(process.env.BNB_FRESH_LIMIT_S ?? 15);
const POLL_INTERVAL_S = Number(process.env.BNB_POLL_INTERVAL_S ?? 30);

async function fetchLatestBlock(endpoint, signal) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0", id: 1,
      method: "eth_getBlockByNumber",
      params: ["latest", false],
    }),
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = await res.json();
  if (body.error) throw new Error(body.error.message);
  const block = body.result;
  if (!block?.timestamp) throw new Error("no block in response");
  return {
    number: Number(BigInt(block.number)),
    timestamp: Number(BigInt(block.timestamp)),
  };
}

async function checkEndpoint(endpoint) {
  const started = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const block = await fetchLatestBlock(endpoint, controller.signal);
    const now = Math.floor(Date.now() / 1000);
    const age = now - block.timestamp;
    return {
      endpoint,
      ok: true,
      latencyMs: Date.now() - started,
      blockNumber: block.number,
      blockAgeSeconds: age,
      fresh: age <= FRESH_LIMIT_S,
    };
  } catch (err) {
    return { endpoint, ok: false, error: String(err.message ?? err) };
  } finally {
    clearTimeout(timer);
  }
}

async function runOnce() {
  const results = await Promise.all(ENDPOINTS.map(checkEndpoint));
  const report = {
    checkedAt: new Date().toISOString(),
    freshLimitSeconds: FRESH_LIMIT_S,
    endpoints: results,
    allFresh: results.every((r) => r.ok && r.fresh),
  };
  console.log(JSON.stringify(report, null, 2));
  return report;
}

if (process.argv.includes("--once")) {
  await runOnce();
} else {
  for (;;) {
    await runOnce().catch((err) =>
      console.error(JSON.stringify({ fatal: String(err.message ?? err) }))
    );
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_S * 1000));
  }
}

