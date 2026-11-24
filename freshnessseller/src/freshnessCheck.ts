const TTL_SECONDS = 300;
const REQUEST_TIMEOUT_MS = 5_000;
const MAX_FUTURE_SKEW_MS = 2_000;

const BINANCE_ENDPOINT = ["https:", "", "api.binance.com", "api", "v3", "trades"].join("/");

export type FreshnessResult = {
  skill: "check_freshness";
  symbol: string;
  status: "FRESH" | "STALE_NO_CHARGE" | "SOURCE_UNAVAILABLE";
  purchaseAllowed: boolean;
  source: "Binance Spot REST /api/v3/trades";
  ttlSeconds: number;
  checkedAtMs: number;
  eventTimestampMs?: number;
  ageMs?: number;
  ageSeconds?: number;
  expiresAtMs?: number;
  reason?: string;
};

type BinanceTrade = {
  time?: unknown;
};

export function evaluateFreshness(
  eventTimestampMs: number,
  nowMs: number,
  ttlSeconds = TTL_SECONDS,
): Pick<
  FreshnessResult,
  "status" | "purchaseAllowed" | "ageMs" | "ageSeconds" | "expiresAtMs" | "reason"
> {
  if (
    !Number.isSafeInteger(eventTimestampMs) ||
    eventTimestampMs <= 0 ||
    !Number.isFinite(nowMs) ||
    !Number.isFinite(ttlSeconds) ||
    ttlSeconds <= 0
  ) {
    return {
      status: "SOURCE_UNAVAILABLE",
      purchaseAllowed: false,
      reason: "invalid_timestamp",
    };
  }

  const ageMs = nowMs - eventTimestampMs;

  if (ageMs < -MAX_FUTURE_SKEW_MS) {
    return {
      status: "SOURCE_UNAVAILABLE",
      purchaseAllowed: false,
      ageMs,
      reason: "exchange_timestamp_is_in_the_future",
    };
  }

  const safeAgeMs = Math.max(0, ageMs);
  const expiresAtMs = eventTimestampMs + ttlSeconds * 1_000;

  if (safeAgeMs > ttlSeconds * 1_000) {
    return {
      status: "STALE_NO_CHARGE",
      purchaseAllowed: false,
      ageMs: safeAgeMs,
      ageSeconds: Math.floor(safeAgeMs / 1_000),
      expiresAtMs,
      reason: "last_trade_exceeds_ttl",
    };
  }

  return {
    status: "FRESH",
    purchaseAllowed: true,
    ageMs: safeAgeMs,
    ageSeconds: Math.floor(safeAgeMs / 1_000),
    expiresAtMs,
  };
}

export async function checkFreshness(
  rawSymbol: unknown,
  fetchImpl: typeof fetch = fetch,
): Promise<FreshnessResult> {
  let checkedAtMs = Date.now();

  if (typeof rawSymbol !== "string") {
    return {
      skill: "check_freshness",
      symbol: "",
      status: "SOURCE_UNAVAILABLE",
      purchaseAllowed: false,
      source: "Binance Spot REST /api/v3/trades",
      ttlSeconds: TTL_SECONDS,
      checkedAtMs,
      reason: "symbol_must_be_a_string",
    };
  }

  const symbol = rawSymbol.trim().toUpperCase();

  if (!/^[A-Z0-9]{5,20}$/.test(symbol)) {
    return {
      skill: "check_freshness",
      symbol,
      status: "SOURCE_UNAVAILABLE",
      purchaseAllowed: false,
      source: "Binance Spot REST /api/v3/trades",
      ttlSeconds: TTL_SECONDS,
      checkedAtMs,
      reason: "invalid_symbol_format",
    };
  }

  try {
    const url = new URL(BINANCE_ENDPOINT);
    url.searchParams.set("symbol", symbol);
    url.searchParams.set("limit", "1");

    const response = await fetchImpl(url, {
      method: "GET",
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });

    if (!response.ok) {
      throw new Error(`Binance HTTP ${response.status}`);
    }

    const payload: unknown = await response.json();
    checkedAtMs = Date.now();

    if (!Array.isArray(payload) || payload.length === 0) {
      throw new Error("Binance returned no recent trades");
    }

    const trade = payload[0] as BinanceTrade;
    const eventTimestampMs = trade?.time;

    if (
      typeof eventTimestampMs !== "number" ||
      !Number.isSafeInteger(eventTimestampMs) ||
      eventTimestampMs <= 0
    ) {
      throw new Error("Binance trade timestamp is invalid");
    }

    const evaluated = evaluateFreshness(
      eventTimestampMs,
      checkedAtMs,
      TTL_SECONDS,
    );

    return {
      skill: "check_freshness",
      symbol,
      source: "Binance Spot REST /api/v3/trades",
      ttlSeconds: TTL_SECONDS,
      checkedAtMs,
      eventTimestampMs,
      ...evaluated,
    };
  } catch (error) {
    return {
      skill: "check_freshness",
      symbol,
      status: "SOURCE_UNAVAILABLE",
      purchaseAllowed: false,
      source: "Binance Spot REST /api/v3/trades",
      ttlSeconds: TTL_SECONDS,
      checkedAtMs,
      reason:
        error instanceof Error ? error.message : "unknown_source_error",
    };
  }
}
