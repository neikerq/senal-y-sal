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
LOG = ROOT / "senales.csv"
TZ = "America/Caracas"
LOG_COLS = ["cierre_vela", "par", "tf", "estrategia", "lado", "entrada", "sl", "tp",
            "estado", "r", "salida_hora"]


def log_signal(close_time, sym, tf, name, side, entry, sl, rr):
    tp = entry + side * rr * abs(entry - sl)
    new = not LOG.exists()
    with LOG.open("a") as f:
        if new:
            f.write(",".join(LOG_COLS) + "\n")
        f.write(f"{close_time.isoformat()},{sym},{tf},{name},{side},{entry},{sl},{tp},abierta,,\n")


def fmt(p):
    d = 2 if p >= 1000 else 3 if p >= 10 else 4 if p >= 1 else 5 if p >= 0.01 else 7
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


def buttons(sym, tf):
    tv_int = {"5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240", "1d": "D"}[tf]
    return {"inline_keyboard": [[
        {"text": "📈 Abrir en Binance", "url": f"https://www.binance.com/es-LA/futures/{sym}"},
        {"text": "📊 TradingView",
         "url": f"https://es.tradingview.com/chart/?symbol=BINANCE:{sym}.P&interval={tv_int}"},
    ]]}


def send_photo(path, caption, markup=None):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    print(caption, f"\n[gráfico: {path}]\n")
    if not token or not chat:
        print("(sin TELEGRAM_TOKEN / TELEGRAM_CHAT_ID: no se envía)")
        return
    payload = {"chat_id": chat, "caption": caption, "parse_mode": "HTML"}
    if markup:
        payload["reply_markup"] = json.dumps(markup)
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                          data=payload, files={"photo": f}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram respondió {r.status_code}: {r.text[:300]}")


def notify(df, sig_pos, sym, tf, name, side, entry, sl, rr, close_time, cfg, prefix=""):
    """Manda la señal con gráfico y botones; si el gráfico falla, solo texto."""
    text = prefix + message(sym, tf, name, side, entry, sl, rr, close_time, cfg)
    tp = entry + side * rr * abs(entry - sl)
    try:
        from .chart import render
        from .strategies import supertrend
        if name.startswith("supertrend"):
            st_dir, st_line = supertrend(df)
        else:
            st_dir = pd.Series(0, index=df.index)
            st_line = pd.Series(float("nan"), index=df.index)
        path = render(df, st_dir, st_line, side, entry, sl, tp,
                      f"{sym} · {tf} · {'LONG' if side == 1 else 'SHORT'}",
                      f"/tmp/{sym}_{tf}.png", signal_idx=sig_pos)
        send_photo(path, text, buttons(sym, tf))
    except Exception as e:  # el aviso no se pierde aunque falle el gráfico
        print(f"Gráfico falló: {e}")
        send(text)


def message(sym, tf, name, side, entry, sl, rr, close_time, cfg):
    risk = abs(entry - sl)
    tp = entry + side * rr * risk
    risk_pct = risk / entry * 100
    size = cfg["position_usdt"]
    age = (pd.Timestamp.now(tz="UTC") - close_time).total_seconds() / 60
    head = "🟢 <b>LONG</b>" if side == 1 else "🔴 <b>SHORT</b>"
    lines = []
    if cfg.get("paper"):
        lines.append("📝 <i>Prueba sin dinero: no operar, solo se registra.</i>")
    lines += [
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
                notify(df, df.index.get_loc(t), sym, tf, name, int(row["side"]),
                       entry, row["sl"], row["rr"], close_time, cfg)
                log_signal(close_time, sym, tf, name, int(row["side"]), entry,
                           row["sl"], row["rr"])
                sent += 1
            state[key] = sig.index[-1].isoformat()
    return sent


def example(cfg):
    item = cfg["strategies"][0]
    name, tf = item["name"], item["tf"]
    for sym in item["symbols"]:
        df = data.recent(sym, tf, 1000)
        sig = run(name, df, tf)
        cand = sig[(sig["side"] != 0) & sig["sl"].notna()]
        for t, row in cand[::-1].iterrows():
            entry = df.at[t, "close"]
            risk_pct = abs(entry - row["sl"]) / entry * 100
            if cfg["min_risk_pct"] <= risk_pct <= cfg["max_risk_pct"]:
                close_time = t + pd.Timedelta(TF_DELTA[tf])
                prefix = "🧪 <b>EJEMPLO</b>: señal pasada, para ver el formato. No operar.\n\n"
                c = dict(cfg, max_signal_age_min=10**9)
                notify(df, df.index.get_loc(t), sym, tf, name, int(row["side"]), entry,
                       row["sl"], row["rr"], close_time, c, prefix=prefix)
                return
    send("🧪 No encontré señales recientes para el ejemplo.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--ejemplo", action="store_true",
                    help="manda la última señal pasada como ejemplo (no se registra)")
    a = ap.parse_args()
    cfg = json.loads(CONFIG.read_text())
    if a.ejemplo:
        example(cfg)
        return
    if a.test:
        names = ", ".join(f"{s['name']} {s['tf']} {'/'.join(s['symbols'])}" for s in cfg["strategies"])
        modo = "prueba sin dinero" if cfg.get("paper") else "real"
        send(f"✅ Bot de señales conectado ({modo}).\nVigilando: {names}")
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    n = check(cfg, state)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    print(f"Señales enviadas: {n}")


if __name__ == "__main__":
    main()
