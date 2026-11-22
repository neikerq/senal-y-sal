"""Backtest de todas las estrategias con datos reales de Binance.

Uso:  python -m bot.backtest --days 365 --symbols XRPUSDT DOGEUSDT --tfs 15m 1h

Supuestos (conservadores):
- Entrada al cierre de la vela de la señal.
- Una posición a la vez por par y estrategia.
- Si en la misma vela se tocan SL y TP, cuenta como SL.
- Costos por lado: comisión taker 0,05% + deslizamiento 0,02%.
- Se descartan señales con SL a menos de MIN_RISK o a más de MAX_RISK.
Resultados en R (1R = lo que se pierde si toca el SL).
"""
import argparse
import os

import numpy as np
import pandas as pd

from . import data
from .strategies import STRATEGIES, run

COST_PER_SIDE = 0.0005 + 0.0002


def simulate(df, sig, min_risk, max_risk):
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    side, sl, rr = sig["side"].values, sig["sl"].values, sig["rr"].values
    trades = []
    i, n = 0, len(df)
    while i < n - 1:
        s = side[i]
        if s == 0 or np.isnan(sl[i]):
            i += 1
            continue
        entry = close[i]
        risk = (entry - sl[i]) * s
        risk_pct = risk / entry
        if risk <= 0 or risk_pct < min_risk or risk_pct > max_risk:
            i += 1
            continue
        tp = entry + s * rr[i] * risk
        exit_px, j = None, i + 1
        while j < n:
            hit_sl = low[j] <= sl[i] if s == 1 else high[j] >= sl[i]
            hit_tp = high[j] >= tp if s == 1 else low[j] <= tp
            if hit_sl:
                exit_px = sl[i]
                break
            if hit_tp:
                exit_px = tp
                break
            j += 1
        if exit_px is None:  # sigue abierta al final de los datos
            exit_px, j = close[-1], n - 1
        gross_r = (exit_px - entry) * s / risk
        cost_r = COST_PER_SIDE * (entry + exit_px) / risk
        trades.append(
            {
                "time": df.index[i],
                "side": int(s),
                "entry": entry,
                "risk_pct": risk_pct * 100,
                "bars": j - i,
                "r": gross_r - cost_r,
            }
        )
        i = j + 1  # no se abre otra hasta cerrar la anterior
    return pd.DataFrame(trades)


def metrics(t, days):
    if t.empty:
        return {"trades": 0}
    r = t["r"]
    eq = r.cumsum()
    dd = (eq - eq.cummax()).min()
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return {
        "trades": len(r),
        "por_semana": round(len(r) / (days / 7), 1),
        "aciertos_%": round((r > 0).mean() * 100, 1),
        "R_promedio": round(r.mean(), 3),
        "R_total": round(r.sum(), 1),
        "factor_ganancia": round(pos / neg, 2) if neg > 0 else float("inf"),
        "caida_max_R": round(dd, 1),
        "riesgo_medio_%": round(t["risk_pct"].mean(), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--symbols", nargs="+", default=["XRPUSDT", "DOGEUSDT"])
    ap.add_argument("--tfs", nargs="+", default=["15m", "1h"])
    ap.add_argument("--min-risk", type=float, default=0.4, help="% mínimo de SL")
    ap.add_argument("--max-risk", type=float, default=1.5, help="% máximo de SL")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows, all_trades = [], []
    for sym in a.symbols:
        for tf in a.tfs:
            df = data.history(sym, tf, a.days)
            print(f"{sym} {tf}: {len(df)} velas")
            split = df.index[int(len(df) * 0.7)]
            for name in STRATEGIES:
                sig = run(name, df, tf)
                t = simulate(df, sig, a.min_risk / 100, a.max_risk / 100)
                m = metrics(t, a.days)
                if not t.empty:
                    test = t[t["time"] >= split]
                    m["R_prom_ultimo_30%"] = round(test["r"].mean(), 3) if len(test) else None
                    t = t.assign(symbol=sym, tf=tf, strategy=name)
                    all_trades.append(t)
                rows.append({"estrategia": name, "par": sym, "tf": tf, **m})

    res = pd.DataFrame(rows).sort_values("R_promedio", ascending=False, na_position="last")
    res.to_csv(f"{a.out}/resumen.csv", index=False)
    if all_trades:
        pd.concat(all_trades).to_csv(f"{a.out}/operaciones.csv", index=False)

    md = [
        f"# Backtest ({a.days} días, SL entre {a.min_risk}% y {a.max_risk}%)",
        "",
        "Costos incluidos: 0,07% por lado. R_promedio > 0 = gana a largo plazo.",
        "`R_prom_ultimo_30%` = solo el último 30% del período: si se mantiene, el resultado es más confiable.",
        "",
        res.to_markdown(index=False),
    ]
    text = "\n".join(md)
    with open(f"{a.out}/resumen.md", "w") as f:
        f.write(text)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
