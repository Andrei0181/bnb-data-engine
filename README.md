# bnb-data-engine

BNB Data Engine — freshness monitoring for BNB Chain RPC endpoints.

## What it does

Polls BSC JSON-RPC endpoints, fetches the latest block, and measures its age
(timestamp of the block vs current time). Reports per-endpoint status as JSON.

## BNB Chain integration

- Default endpoints: official public BSC dataseed nodes (mainnet).
- Override with `BNB_RPC_ENDPOINTS` (comma-separated list).
- Freshness threshold: `BNB_FRESH_LIMIT_S` (default 15 s — one block slot).
- Poll interval: `BNB_POLL_INTERVAL_S` (default 30 s).

## Usage

    npm start            # continuous monitoring
    node src/engine.mjs --once   # single check, JSON to stdout

## Status

v0.1.0 — freshness monitor. Planned: WebSocket subscriptions, log indexing,
freshness-guaranteed data API (see docs).

