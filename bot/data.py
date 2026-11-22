"""Descarga de velas públicas de Binance (sin API key)."""
import time

import pandas as pd
import requests

# data-api.binance.vision es el endpoint público de datos de mercado de Binance.
BASES = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]

INTERVAL_MS = {
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


def _get(path, params):
    last_err = None
    for base in BASES:
        for attempt in range(3):
            try:
                r = requests.get(base + path, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                last_err = f"{base} -> HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code in (418, 429):
                    time.sleep(5 * (attempt + 1))
                    continue
                break
            except requests.RequestException as e:
                last_err = f"{base} -> {e}"
                time.sleep(2)
    raise RuntimeError(f"No se pudieron leer las velas: {last_err}")


def _to_df(rows):
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qv", "n", "tbv", "tqv", "ign",
        ],
    )
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.drop_duplicates("open_time").set_index("open_time").sort_index()
    return df[["open", "high", "low", "close", "volume", "close_time"]]


def recent(symbol, interval, limit=1000):
    """Últimas `limit` velas. Quita la vela que todavía está abierta."""
    rows = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    df = _to_df(rows)
    now = pd.Timestamp.now(tz="UTC")
    return df[df["close_time"] < now]


def history(symbol, interval, days):
    """Velas cerradas de los últimos `days` días (paginando de a 1000)."""
    step = INTERVAL_MS[interval]
    end = int(time.time() * 1000)
    start = end - days * 24 * 60 * 60_000
    rows = []
    cur = start
    while cur < end:
        chunk = _get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "startTime": cur, "limit": 1000},
        )
        if not chunk:
            break
        rows.extend(chunk)
        cur = chunk[-1][0] + step
        if len(chunk) < 1000:
            break
        time.sleep(0.2)
    df = _to_df(rows)
    now = pd.Timestamp.now(tz="UTC")
    return df[df["close_time"] < now]


def since(symbol, interval, start):
    """Velas cerradas desde `start` (Timestamp UTC) hasta ahora."""
    step = INTERVAL_MS[interval]
    cur = int(pd.Timestamp(start).timestamp() * 1000)
    end = int(time.time() * 1000)
    rows = []
    while cur < end:
        chunk = _get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "startTime": cur, "limit": 1000},
        )
        if not chunk:
            break
        rows.extend(chunk)
        cur = chunk[-1][0] + step
        if len(chunk) < 1000:
            break
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "close_time"])
    df = _to_df(rows)
    now = pd.Timestamp.now(tz="UTC")
    return df[df["close_time"] < now]
