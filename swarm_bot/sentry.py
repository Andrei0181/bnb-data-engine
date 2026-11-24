#!/usr/bin/env python3
# sentry.py — страж данных: проверяет agent_*.json и commands.jsonl
import sys, os, json, glob, time

TTL_S = 300      # секунд жизни записи
DRIFT_TOL = 0.5  # % — максимальный дрейф цены
Z_MAX = 20.0     # граница разумного z
FAKE_FIELDS = {"bestBid", "bestAsk"}  # несуществующие в API Binance

errors, warnings = [], []
def add(lvl, path, msg):
    (errors if lvl == "E" else warnings).append(f"{path}: {msg}")

def parse_ts(v):
    try: v = float(v)
    except (TypeError, ValueError): return None
    if v > 1e12: return v / 1000.0   # миллисекунды
    if v > 1e9:  return v            # секунды
    return None

now = time.time()
src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/swarm"
files = sorted(glob.glob(os.path.join(src, "agent_*.json")))
report = {"checked": 0, "errors": errors, "warnings": warnings, "duplicates": {}}
seen = {}

for f in files:
    p = os.path.basename(f)
    try:
        d = json.load(open(f))
    except Exception as e:
        add("E", p, f"битый JSON: {e}"); continue
    report["checked"] += 1
    for k in d:
        if isinstance(k, str) and k in FAKE_FIELDS:
            add("E", p, f"несуществующее поле API: {k}")
    ts = parse_ts(d.get("timestamp") or d.get("ts"))
    age = d.get("ageSeconds")
    if ts:
        if ts > now + 60:
            add("E", p, "таймстамп из будущего")
        real = now - ts
        if isinstance(age, (int, float)) and abs(age - real) > 30:
            add("E", p, f"враньё о возрасте: ageSeconds={age}, реально {real:.0f}s")
        if real > TTL_S:
            add("W", p, f"протух: {real:.0f}s > {TTL_S}s")
    sig, pr = d.get("signalPrice"), d.get("price")
    if sig and pr:
        try:
            drift = abs(float(pr) - float(sig)) / float(sig) * 100
            claimed = d.get("priceDrift")
            if claimed is not None and abs(float(claimed) - drift) > 0.01:
                add("E", p, f"дрейф не сходится: заявлен {claimed}%, пересчёт {drift:.4f}%")
        except (TypeError, ValueError):
            add("E", p, "signalPrice/price — не числа")
    z = d.get("z")
    if z is not None:
        try:
            zf = float(z)
            if zf != zf: add("E", p, "z = NaN")
            elif abs(zf) > Z_MAX: add("W", p, f"z вне границы: {zf}")
        except (TypeError, ValueError):
            add("E", p, "z — не число")
    pair = d.get("pair") or d.get("symbol")
    if pair: seen[pair] = seen.get(pair, 0) + 1

for k, v in seen.items():
    if v > 1:
        add("W", "agents", f"дубли пары {k}: {v} файлов")
        report["duplicates"][k] = v

cmds = os.path.join(os.path.expanduser("~"), "swarm_bot", "commands.jsonl")
if os.path.exists(cmds):
    for i, line in enumerate(open(cmds), 1):
        line = line.strip()
        if not line: continue
        try:
            c = json.loads(line)
        except Exception as e:
            add("E", f"commands.jsonl:{i}", f"битая строка: {e}"); continue
        ts = parse_ts(c.get("ts") or c.get("timestamp"))
        if ts and now - ts > TTL_S:
            add("W", f"commands.jsonl:{i}", f"stale: {now - ts:.0f}s > {TTL_S}s")

print(f"=== SENTRY {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
print(f"checked: {report['checked']} files | errors: {len(errors)} | warnings: {len(warnings)}")
for e in errors:   print("[ERROR]", e)
for w in warnings: print("[WARN ]", w)
with open("sentry_report.json", "w") as fh:
    json.dump(report, fh, indent=2, ensure_ascii=False)
sys.exit(1 if errors else 0)
