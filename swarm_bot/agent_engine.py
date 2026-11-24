import numpy as np
import random
from collections import deque

CFG = {
    "alpha": 0.02,
    "k_entry": 2.2,
    "k_exit": 0.3,
    "stop_loss_z": 4.5,
    "commission": 0.0002,     # 0.02% Maker (Post-Only)
    "min_edge_mult": 3.0,     # Ожидаемый профит должен быть минимум в 3 раза больше комиссий
    "initial_balance": 4150.0
}

class RegState:
    def __init__(self):
        self.beta = 1.0
        self.intercept = 0.0
        self.mean_x = 0.0
        self.mean_y = 0.0
        self.M2_x = 0.0
        self.M2_y = 0.0
        self.M2_xy = 0.0
        self.sigma = 0.0
        self.z_score = 0.0
        self.count = 0
        self.degraded = False

def update_welford_streaming(state: RegState, x: float, y: float, cfg: dict):
    alpha = cfg["alpha"]
    state.count += 1
    dx = x - state.mean_x
    dy = y - state.mean_y
    state.mean_x += alpha * dx
    state.mean_y += alpha * dy
    state.M2_x = (1 - alpha) * state.M2_x + alpha * (dx * (x - state.mean_x))
    state.M2_y = (1 - alpha) * state.M2_y + alpha * (dy * (y - state.mean_y))
    state.M2_xy = (1 - alpha) * state.M2_xy + alpha * (dx * (y - state.mean_y))

    if state.M2_x < 1e-6:
        state.degraded = True
        return 0.0, state

    state.beta = state.M2_xy / state.M2_x
    state.intercept = state.mean_y - (state.beta * state.mean_x)
    var_res = state.M2_y - (state.beta * state.M2_xy)
    state.sigma = np.sqrt(max(0.0, var_res))

    if state.sigma < 1e-4 or not np.isfinite(state.beta):
        state.degraded = True
        return 0.0, state

    spread = y - (state.beta * x + state.intercept)
    state.z_score = spread / state.sigma
    state.degraded = False
    return state.z_score, state

class CorrelationFilter:
    def __init__(self, window_size=50, threshold=0.7):
        self.window_size = window_size
        self.threshold = threshold
        self.history_a = deque(maxlen=window_size)
        self.history_b = deque(maxlen=window_size)

    def update(self, price_a, price_b):
        self.history_a.append(price_a)
        self.history_b.append(price_b)

    def get_corr(self):
        if len(self.history_a) < self.window_size:
            return 0.0
        corr = np.corrcoef(self.history_a, self.history_b)[0, 1]
        return float(corr) if np.isfinite(corr) else 0.0

def run_replay(data):
    state = RegState()
    corr_filter = CorrelationFilter()
    balance = CFG["initial_balance"]
    position = 0
    qty_x = 0.0
    qty_y = 0.0
    entry_x = 0.0
    entry_y = 0.0
    trades = []

    for i, tick in enumerate(data):
        pa, pb = tick['price_a'], tick['price_b']
        z_score, state = update_welford_streaming(state, pa, pb, CFG)
        corr_filter.update(pa, pb)

        if i < 100 or state.degraded:
            continue

        corr = corr_filter.get_corr()

        # Фильтр рентабельности: отклонение спреда (sigma * k_entry) должно перекрывать комиссии
        expected_move_pct = (state.sigma * CFG["k_entry"]) / pb
        roundtrip_fee_pct = CFG["commission"] * 4  # вход и выход по двум ногам

        if position == 0 and corr > corr_filter.threshold:
            if abs(z_score) > CFG["k_entry"] and expected_move_pct > (roundtrip_fee_pct * CFG["min_edge_mult"]):
                position = -1 if z_score > 0 else 1
                weight_mult = min(1.0, max(0.5, (corr - 0.5) * 2.0))
                leg_notional = (balance * 0.25) * weight_mult

                qty_y = position * (leg_notional / pb)
                qty_x = -position * ((leg_notional * abs(state.beta)) / pa)
                entry_x, entry_y = pa, pb

                fee = (abs(qty_x * pa) + abs(qty_y * pb)) * CFG["commission"]
                balance -= fee

        elif position != 0:
            if abs(z_score) < CFG["k_exit"] or abs(z_score) > CFG["stop_loss_z"] or corr < 0.4:
                pnl_y = qty_y * (pb - entry_y)
                pnl_x = qty_x * (pa - entry_x)
                fee = (abs(qty_x * pa) + abs(qty_y * pb)) * CFG["commission"]
                net_pnl = pnl_x + pnl_y - fee

                balance += net_pnl
                trades.append(net_pnl)
                position, qty_x, qty_y = 0, 0.0, 0.0

    win_rate = len([t for t in trades if t > 0]) / len(trades) if trades else 0.0
    return {
        "final_balance": round(float(balance), 2),
        "pnl": round(float(balance - CFG["initial_balance"]), 2),
        "trades": len(trades),
        "win_rate": round(win_rate * 100, 1)
    }

if __name__ == "__main__":
    random.seed(42)
    pa, pb = 100.0, 150.0
    sample_data = []
    for i in range(1500):
        pa += random.gauss(0, 0.2)
        pb = pa * 1.5 + np.sin(i / 15.0) * 1.2 + random.gauss(0, 0.15)
        sample_data.append({"price_a": pa, "price_b": pb})
    print("Результат теста (после фикса intercept + фильтр комиссий):", run_replay(sample_data))
