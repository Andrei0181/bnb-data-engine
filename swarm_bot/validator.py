import time, json, sys

MAX_AGE_SECONDS = 120

def validate_signal(signal: dict, current_price=None) -> dict:
    ts = signal.get("timestamp", 0)
    now_ms = time.time() * 1000
    age = (now_ms - ts) / 1000

    if not (0 <= age <= MAX_AGE_SECONDS):
        return {"isValid": False, "reason": f"stale signal: age {age:.0f}s"}

    if current_price is not None:
        drift = abs(signal["signalPrice"] - current_price) / current_price * 100
        if drift > 1.0:
            return {"isValid": False, "reason": f"price drift {drift:.2f}%"}

    return {"isValid": True, "reason": "ok"}

if __name__ == "__main__":
    s = json.load(open(sys.argv[1]))["signal"]
    print(json.dumps(validate_signal(s, current_price=None),
                     ensure_ascii=False, indent=2))
