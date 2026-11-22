"""Revisa las señales registradas en senales.csv: marca cuáles tocaron TP o SL
y manda a Telegram un resumen del resultado en R.

Uso:  python -m bot.seguimiento            (actualiza y manda resumen)
      python -m bot.seguimiento --silencio (solo actualiza)
"""
import argparse

import pandas as pd

from . import data
from .backtest import COST_PER_SIDE
from .signals import LOG, LOG_COLS, TZ, send


def grade(row):
    """Devuelve (estado, r, hora_salida) mirando las velas posteriores a la señal."""
    start = pd.Timestamp(row["cierre_vela"])
    df = data.since(row["par"], row["tf"], start)
    side, entry, sl, tp = int(row["lado"]), row["entrada"], row["sl"], row["tp"]
    risk = abs(entry - sl)
    for t, c in df.iterrows():
        hit_sl = c["low"] <= sl if side == 1 else c["high"] >= sl
        hit_tp = c["high"] >= tp if side == 1 else c["low"] <= tp
        if hit_sl or hit_tp:
            px = sl if hit_sl else tp  # si toca las dos en la misma vela, cuenta SL
            r = (px - entry) * side / risk - COST_PER_SIDE * (entry + px) / risk
            return ("tp" if not hit_sl else "sl"), round(r, 3), c["close_time"].isoformat()
    return "abierta", None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--silencio", action="store_true")
    a = ap.parse_args()
    if not LOG.exists():
        if not a.silencio:
            send("📊 Seguimiento: todavía no hay señales registradas.")
        return
    log = pd.read_csv(LOG, dtype={"estado": str, "salida_hora": str})
    for i, row in log.iterrows():
        if row["estado"] == "abierta":
            estado, r, hora = grade(row)
            log.at[i, "estado"], log.at[i, "r"], log.at[i, "salida_hora"] = estado, r, hora
    log[LOG_COLS].to_csv(LOG, index=False)

    closed = log[log["estado"].isin(["tp", "sl"])]
    abiertas = (log["estado"] == "abierta").sum()
    if a.silencio:
        return
    lines = ["📊 <b>Seguimiento de señales</b> (prueba sin dinero)"]
    if closed.empty:
        lines.append(f"Cerradas: 0 · abiertas: {abiertas}")
    else:
        r = closed["r"].astype(float)
        lines += [
            f"Cerradas: {len(r)} · abiertas: {abiertas}",
            f"TP: {(closed['estado'] == 'tp').sum()} · SL: {(closed['estado'] == 'sl').sum()}"
            f" · aciertos {(r > 0).mean() * 100:.0f}%",
            f"Total: <b>{r.sum():+.2f}R</b> · promedio {r.mean():+.3f}R por operación",
            f"Backtest esperado: ~+0,06 a +0,16R por operación",
            "",
            "<b>Por par</b>",
        ]
        for par, g in closed.groupby("par"):
            lines.append(f"{par}: {len(g)} op · {g['r'].astype(float).sum():+.2f}R")
        last = closed.tail(5)
        lines += ["", "<b>Últimas cerradas</b>"]
        for _, x in last.iterrows():
            t = pd.Timestamp(x["cierre_vela"]).tz_convert(TZ)
            lado = "L" if int(x["lado"]) == 1 else "S"
            lines.append(f"{t:%d/%m %H:%M} {x['par']} {lado} → {x['estado'].upper()} {float(x['r']):+.2f}R")
    send("\n".join(lines))


if __name__ == "__main__":
    main()
