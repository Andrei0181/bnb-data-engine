import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { checkFreshness, evaluateFreshness } from "../src/freshnessCheck.ts";

const TTL = 300;
const EVENT = 1_000_000;

// ---------- evaluateFreshness: границы TTL ----------

describe("evaluateFreshness: границы TTL", () => {
  it("299 999 мс — FRESH", () => {
    const r = evaluateFreshness(EVENT, EVENT + 299_999, TTL);
    assert.equal(r.status, "FRESH");
    assert.equal(r.purchaseAllowed, true);
  });

  it("ровно 300 000 мс — ещё FRESH (сравнение строго >)", () => {
    const r = evaluateFreshness(EVENT, EVENT + 300_000, TTL);
    assert.equal(r.status, "FRESH");
    assert.equal(r.purchaseAllowed, true);
  });

  it("300 001 мс — STALE_NO_CHARGE", () => {
    const r = evaluateFreshness(EVENT, EVENT + 300_001, TTL);
    assert.equal(r.status, "STALE_NO_CHARGE");
    assert.equal(r.purchaseAllowed, false);
    assert.equal(r.reason, "last_trade_exceeds_ttl");
  });

  it("усечение вниз: 299 700 мс → ageSeconds 299", () => {
    const r = evaluateFreshness(EVENT, EVENT + 299_700, TTL);
    assert.equal(r.ageMs, 299_700);
    assert.equal(r.ageSeconds, 299);
  });

  it("expiresAtMs = метка события + TTL*1000", () => {
    const r = evaluateFreshness(EVENT, EVENT + 1_000, TTL);
    assert.equal(r.expiresAtMs, EVENT + 300_000);
  });
});

// ---------- evaluateFreshness: часы из будущего ----------

describe("evaluateFreshness: рассинхрон часов", () => {
  it("в будущее на 1 999 мс — зажимается в 0, FRESH", () => {
    const r = evaluateFreshness(EVENT, EVENT - 1_999, TTL);
    assert.equal(r.status, "FRESH");
    assert.equal(r.ageMs, 0);
  });

  it("ровно 2 000 мс в будущее — на границе допуска, FRESH", () => {
    const r = evaluateFreshness(EVENT, EVENT - 2_000, TTL);
    assert.equal(r.status, "FRESH");
    assert.equal(r.ageMs, 0);
  });

  it("2 001 мс в будущее — SOURCE_UNAVAILABLE", () => {
    const r = evaluateFreshness(EVENT, EVENT - 2_001, TTL);
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.purchaseAllowed, false);
    assert.equal(r.reason, "exchange_timestamp_is_in_the_future");
    assert.equal(r.ageMs, -2_001);
  });
});

// ---------- evaluateFreshness: некорректные входные данные ----------

describe("evaluateFreshness: некорректные входные данные", () => {
  const cases: Array<[string, number, number, number]> = [
    ["NaN вместо метки события", Number.NaN, 1_000_000, TTL],
    ["нулевая метка события", 0, 1_000_000, TTL],
    ["отрицательная метка события", -5, 1_000_000, TTL],
    ["нецелая метка события", 1000.5, 1_000_000, TTL],
    ["ttl = 0", EVENT, 1_000_000, 0],
    ["отрицательный ttl", EVENT, 1_000_000, -1],
  ];

  for (const [name, event, now, ttl] of cases) {
    it(name + " → invalid_timestamp", () => {
      const r = evaluateFreshness(event, now, ttl);
      assert.equal(r.status, "SOURCE_UNAVAILABLE");
      assert.equal(r.purchaseAllowed, false);
      assert.equal(r.reason, "invalid_timestamp");
    });
  }
});

// ---------- checkFreshness: валидация символа ----------

describe("checkFreshness: валидация символа без сети", () => {
  const neverFetch = async () => {
    throw new Error("fetch не должен вызываться");
  };

  it("не-строка → symbol_must_be_a_string", async () => {
    const r = await checkFreshness(42, neverFetch);
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "symbol_must_be_a_string");
  });

  it("слишком короткий символ → invalid_symbol_format", async () => {
    const r = await checkFreshness("AB", neverFetch);
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "invalid_symbol_format");
  });

  it("запрещённые символы → invalid_symbol_format", async () => {
    const r = await checkFreshness("BTC-USDT!", neverFetch);
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "invalid_symbol_format");
  });

  it("пробелы и регистр: ' btcusdt ' → BTCUSDT", async () => {
    const now = Date.now();
    const fetchOk = async () => ({
      ok: true,
      json: async () => [{ time: now - 10_000 }],
    });
    const r = await checkFreshness(" btcusdt ", fetchOk);
    assert.equal(r.symbol, "BTCUSDT");
    assert.equal(r.status, "FRESH");
  });
});

// ---------- checkFreshness: шина ошибок источника ----------

describe("checkFreshness: шина ошибок источника", () => {
  it("HTTP 500 → SOURCE_UNAVAILABLE с текстом ошибки", async () => {
    const r = await checkFreshness("BTCUSDT", async () => ({
      ok: false,
      status: 500,
      json: async () => ({}),
    }));
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "Binance HTTP 500");
  });

  it("пустой массив сделок → SOURCE_UNAVAILABLE", async () => {
    const r = await checkFreshness("BTCUSDT", async () => ({
      ok: true,
      json: async () => [],
    }));
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "Binance returned no recent trades");
  });

  it("нечисловое поле time → SOURCE_UNAVAILABLE", async () => {
    const r = await checkFreshness("BTCUSDT", async () => ({
      ok: true,
      json: async () => [{ time: "не-число" }],
    }));
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "Binance trade timestamp is invalid");
  });

  it("сетевой отказ → SOURCE_UNAVAILABLE с текстом исключения", async () => {
    const r = await checkFreshness("BTCUSDT", async () => {
      throw new Error("сеть недоступна");
    });
    assert.equal(r.status, "SOURCE_UNAVAILABLE");
    assert.equal(r.reason, "сеть недоступна");
  });
});

// ---------- checkFreshness: успешный путь ----------

describe("checkFreshness: успешный путь", () => {
  it("полный корректный ответ", async () => {
    const now = Date.now();
    const fetchOk = async () => ({
      ok: true,
      json: async () => [{ time: now - 60_000 }],
    });
    const r = await checkFreshness("BTCUSDT", fetchOk);
    assert.equal(r.skill, "check_freshness");
    assert.equal(r.symbol, "BTCUSDT");
    assert.equal(r.source, "Binance Spot REST /api/v3/trades");
    assert.equal(r.ttlSeconds, TTL);
    assert.equal(r.eventTimestampMs, now - 60_000);
    assert.equal(r.status, "FRESH");
    assert.equal(r.purchaseAllowed, true);
    assert.equal(r.expiresAtMs, now - 60_000 + TTL * 1_000);
  });

  it("свежая сделка 299 с назад — FRESH через сеть", async () => {
    const now = Date.now();
    const fetchOk = async () => ({
      ok: true,
      json: async () => [{ time: now - 299_000 }],
    });
    const r = await checkFreshness("ETHUSDT", fetchOk);
    assert.equal(r.status, "FRESH");
  });

  it("сделка 301 с назад — STALE_NO_CHARGE через сеть", async () => {
    const now = Date.now();
    const fetchOk = async () => ({
      ok: true,
      json: async () => [{ time: now - 301_000 }],
    });
    const r = await checkFreshness("ETHUSDT", fetchOk);
    assert.equal(r.status, "STALE_NO_CHARGE");
    assert.equal(r.purchaseAllowed, false);
  });
});
