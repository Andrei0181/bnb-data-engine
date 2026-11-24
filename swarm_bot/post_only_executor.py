import os, json, time, hmac, hashlib, requests
from decimal import Decimal, ROUND_DOWN

BASE = "https://api-demo.bybit.com"
K, S = os.getenv("API_KEY",""), os.getenv("API_SECRET","")
DELTA = "/tmp/swarm_net_delta.json"
WHITELIST = {"BTCUSDT","ETHUSDT","SOLUSDT","AVAXUSDT","ARBUSDT","TIAUSDT","ATOMUSDT","OPUSDT","UNIUSDT","1INCHUSDT"}
LINK = "SW-"
MIN_NOTIONAL = 5.0          # биржевой минимум, не наш порог
DELTA_MAX_AGE = 20          # сек: дельта старше -> ничего не делаем
_cache = {}

def sign(p): return hmac.new(S.encode(), p.encode(), hashlib.sha256).hexdigest()

def hdr(ts, payload):
    return {"X-BAPI-API-KEY": K, "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": "5000", "X-BAPI-SIGN": sign(payload)}

def api(method, path, params=None, body=None):
    ts = str(int(time.time()*1000))
    if method == "GET":
        q = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        r = requests.get(f"{BASE}{path}" + (f"?{q}" if q else ""),
                         headers=hdr(ts, ts+K+"5000"+q), timeout=8)
    else:
        b = json.dumps(body, separators=(",", ":"))
        r = requests.post(f"{BASE}{path}",
                          headers={**hdr(ts, ts+K+"5000"+b), "Content-Type":"application/json"},
                          data=b, timeout=8)
    return r.json()

def specs(sym):
    """Шаг лота/цены с биржи. Нет данных -> исключение, НИКАКИХ fallback 0.001."""
    c = _cache.get(sym)
    if c and time.time()-c["ts"] < 3600: return c
    r = api("GET", "/v5/market/instruments-info", {"category":"linear","symbol":sym})
    if r.get("retCode") != 0: raise RuntimeError(f"specs {sym}: {r.get('retMsg')}")
    lst = r["result"]["list"]
    if not lst: raise RuntimeError(f"{sym} отсутствует в instruments-info")
    it = lst[0]
    c = {"ts": time.time(),
         "step": Decimal(it["lotSizeFilter"]["qtyStep"]),
         "min":  Decimal(it["lotSizeFilter"]["minOrderQty"]),
         "tick": Decimal(it["priceFilter"]["tickSize"])}
    _cache[sym] = c
    return c

def floor_step(v, step):
    n = (Decimal(str(v))/step).to_integral_value(rounding=ROUND_DOWN)
    return n*step

def fmt(d):
    s = format(d.normalize(), "f")
    return s if s not in ("", "-0") else "0"

def book(sym):
    r = api("GET", "/v5/market/orderbook", {"category":"linear","symbol":sym,"limit":"1"})
    if r.get("retCode") != 0: raise RuntimeError(f"book {sym}: {r.get('retMsg')}")
    res = r["result"]
    return Decimal(res["b"][0][0]), Decimal(res["a"][0][0])

def my_orders(sym):
    r = api("GET", "/v5/order/realtime",
            {"category":"linear","symbol":sym,"openOnly":"0","limit":"50"})
    if r.get("retCode") != 0: raise RuntimeError(f"orders {sym}: {r.get('retMsg')}")
    return [o for o in r["result"]["list"] if (o.get("orderLinkId") or "").startswith(LINK)]

def cancel(sym, o):
    api("POST", "/v5/order/cancel",
        body={"category":"linear","symbol":sym,"orderLinkId":o["orderLinkId"]})

print(f"[EXEC] whitelist={sorted(WHITELIST)} PostOnly, без cancel-churn", flush=True)
while True:
    try:
        if not os.path.exists(DELTA) or time.time()-os.path.getmtime(DELTA) > DELTA_MAX_AGE:
            time.sleep(2); continue
        D = json.load(open(DELTA))
        for sym, raw in D.items():
            if sym not in WHITELIST: continue
            try:
                sp = specs(sym)
                bid, ask = book(sym)
                diff = Decimal(str(raw))
                side = "Buy" if diff > 0 else "Sell"
                qty = floor_step(abs(diff), sp["step"])
                px = bid if side == "Buy" else ask
                if qty < sp["min"] or qty*px < Decimal(str(MIN_NOTIONAL)):
                    for o in my_orders(sym): cancel(sym, o)
                    continue
                qs, ps = fmt(qty), fmt(floor_step(px, sp["tick"]))
                live = my_orders(sym)
                # ордер уже стоит с нужными параметрами -> НЕ трогаем, даём налиться
                if any(o["side"]==side and o["qty"]==qs and o["price"]==ps for o in live):
                    continue
                for o in live: cancel(sym, o)
                r = api("POST", "/v5/order/create", body={
                    "category":"linear","symbol":sym,"side":side,"orderType":"Limit",
                    "qty":qs,"price":ps,"timeInForce":"PostOnly",
                    "orderLinkId": f"{LINK}{sym}-{int(time.time())}"})
                rc = r.get("retCode")
                if rc == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ {sym} {side} {qs} @ {ps} "
                          f"(~${qty*px:.2f})", flush=True)
                elif rc == 110007:
                    pass                      # PostOnly пересёк бы стакан — ждём следующий тик
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ❌ {sym} {rc}: {r.get('retMsg')} "
                          f"(qty={qs} px={ps})", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] SKIP {sym}: {e}", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] SKIP цикл: {e}", flush=True)
    time.sleep(3)
