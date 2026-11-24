import subprocess, time, os

def kill_all():
    for name in ["price_feeder", "netting_router", "post_only_executor", "agent_loop"]:
        subprocess.run(["pkill", "-9", "-f", name], capture_output=True)
    time.sleep(1)

print("🚀 Запуск Swarm Stack...")
kill_all()

# Убедимся, что папка существует
os.makedirs("/tmp/swarm", exist_ok=True)

# Загружаем ключи
keys_env = {}
with open(os.path.expanduser("~/swarm_bot/keys.env")) as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            keys_env[k.replace("export ", "")] = v.strip("'\"")

env = os.environ.copy()
env.update(keys_env)

procs = []

# 1. Фидер
p1 = subprocess.Popen(["python3", "-u", "price_feeder.py"], 
                      stdout=open("/tmp/feeder.log", "w"), 
                      stderr=subprocess.STDOUT, env=env)
procs.append(("feeder", p1))
time.sleep(2)

# 2. Роутер
p2 = subprocess.Popen(["python3", "-u", "netting_router.py"], 
                      stdout=open("/tmp/router.log", "w"), 
                      stderr=subprocess.STDOUT, env=env)
procs.append(("router", p2))
time.sleep(2)

# 3. Исполнитель
p3 = subprocess.Popen(["python3", "-u", "post_only_executor.py"], 
                      stdout=open("/tmp/executor.log", "w"), 
                      stderr=subprocess.STDOUT, env=env)
procs.append(("executor", p3))

# 4. Рой агентов (72 шт.)
for i in range(1, 73):
    e = env.copy()
    e["AGENT_ID"] = str(i)
    subprocess.Popen(["python3", "-u", "agent_loop.py"], 
                     stdout=subprocess.DEVNULL, 
                     stderr=subprocess.DEVNULL, env=e)

print(f"✅ Стект поднят. PID фидера: {p1.pid}, роутера: {p2.pid}, исполнителя: {p3.pid}")
print("Логи доступны в /tmp/feeder.log, /tmp/router.log, /tmp/executor.log")
