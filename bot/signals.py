"""Revisa las velas recién cerradas y manda las señales nuevas a Telegram.

Uso:  python -m bot.signals          (revisión normal)
      python -m bot.signals --test   (manda un mensaje de prueba)
"""
import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd
import requests

from . import data
from .strategies import STRATEGIES, TF_DELTA, run

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
STATE = ROOT / "state.json"
TZ = "America/Caracas"


def fmt(p):
    d = 2 if p >= 1000 else 3 if p >= 100 else 4 if p >= 1 else 5 if p >= 0.01 else 7
    return f"{p:.{d}f}"


def send(text):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    print(text, "\n")
    if not token or not chat:
        print("(sin TELEGRAM_TOKEN / TELEGRAM_CHAT_ID: no se envía)")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Telegram respondió {r.status_code}: {r.text[:300]}")


def message(sym, tf, name, side, entry, sl, rr, close_time, cfg):
    risk = abs(entry - sl)
    tp = entry + side * rr * risk
    risk_pct = risk / entry * 100
    size = cfg["position_usdt"]
    age = (pd.Timestamp.now(tz="UTC") - close_time).total_seconds() / 60
    head = "🟢 <b>LONG</b>" if side == 1 else "🔴 <b>SHORT</b>"
    lines = [
        f"{head} {sym}  ({tf} · {name})",
        f"Entrada: <b>{fmt(entry)}</b>  (cierre {close_time.tz_convert(TZ):%d/%m %H:%M})",
        f"SL: <b>{fmt(sl)}</b>  ({'-' if side == 1 else '+'}{risk_pct:.2f}%)",
        f"TP: <b>{fmt(tp)}</b>  ({'+' if side == 1 else '-'}{risk_pct * rr:.2f}%, {rr:g}R)",
        f"Posición {size} USDT → pérdida si toca SL ≈ {size * risk_pct / 100:.3f} USDT",
    ]
    if age > cfg["max_signal_age_min"]:
        lines.append(f"⚠️ Llegó con {age:.0f} min de retraso: revisa el precio antes de entrar.")
    return "\n".join(lines)


def check(cfg, state):
    sent = 0
    for item in cfg["strategies"]:
        name, tf = item["name"], item["tf"]
        for sym in item["symbols"]:
            key = f"{sym}|{tf}|{name}"
            df = data.recent(sym, tf, 1000)
            sig = run(name, df, tf)
            last_done = state.get(key)
            if last_done:
                new = sig[sig.index > pd.Timestamp(last_done)].tail(4)
            else:
                new = sig.tail(1)  # primera vez: solo la última vela
            for t, row in new.iterrows():
                if row["side"] == 0 or math.isnan(row["sl"]):
                    continue
                entry = df.at[t, "close"]
                risk_pct = abs(entry - row["sl"]) / entry * 100
                if not (cfg["min_risk_pct"] <= risk_pct <= cfg["max_risk_pct"]):
                    print(f"{key} {t}: señal descartada, SL a {risk_pct:.2f}%")
                    continue
                close_time = t + pd.Timedelta(TF_DELTA[tf])
                send(message(sym, tf, name, int(row["side"]), entry, row["sl"],
                             row["rr"], close_time, cfg))
                sent += 1
            state[key] = sig.index[-1].isoformat()
    return sent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(CONFIG.read_text())
    if a.test:
        names = ", ".join(f"{s['name']} {s['tf']} {'/'.join(s['symbols'])}" for s in cfg["strategies"])
        send(f"✅ Bot de señales conectado.\nVigilando: {names}")
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    n = check(cfg, state)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    print(f"Señales enviadas: {n}")


if __name__ == "__main__":
    main()
