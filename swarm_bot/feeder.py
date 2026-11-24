#!/usr/bin/env python3
# feeder.py — пишет живые котировки Binance в ~/swarm_bot/data
import json, time, os, sys, urllib.request

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "BNBUSDT"
INTERVAL_S = 5
BASE = os.environ.get("BINANCE_BASE_URL", "https://api.binance.com")
OUT_DIR = os.path.expanduser("~/swarm_bot/data")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_FILE = os.path.join(OUT_DIR, "agent_feeder.json")

while True:
    try:
        with urllib.request.urlopen(
                f"{BASE}/api/v3/ticker/bookTicker?symbol={SYMBOL}", timeout=5) as r:
            d = json.loads(r.read())
        q = {
            "agent": "feeder",
            "symbol": d["symbol"],
            "bidPrice": float(d["bidPrice"]),
            "askPrice": float(d["askPrice"]),
            "bidQty": float(d["bidQty"]),
            "askQty": float(d["askQty"]),
            "timestamp": round(time.time()),  # секунды, честные
            "ageSeconds": 0,
        }
        tmp = OUT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(q, f)
        os.replace(tmp, OUT_FILE)
        print(f"{time.strftime('%H:%M:%S')} {q['symbol']} bid={q['bidPrice']} ask={q['askPrice']}")
    except Exception as e:
        print(f"{time.strftime('%H:%M:%S')} ошибка: {e}", flush=True)
    time.sleep(INTERVAL_S)
