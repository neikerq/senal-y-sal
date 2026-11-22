"""Indicadores y estrategias.

Cada estrategia recibe velas cerradas (DataFrame con open/high/low/close/volume,
índice = hora de apertura UTC) y devuelve un DataFrame alineado con:
  side: 1 = long, -1 = short, 0 = nada   (señal al CIERRE de esa vela)
  sl:   precio del stop loss
La entrada es el cierre de la vela de la señal. El TP = entrada + RR × riesgo.
"""
import numpy as np
import pandas as pd

TF_DELTA = {
    "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "4h": "4h", "1d": "1D",
}


# ---------------------------------------------------------------- indicadores
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    prev = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def supertrend(df, n=10, mult=3.0):
    a = atr(df, n).values
    hl2 = ((df["high"] + df["low"]) / 2).values
    close = df["close"].values
    upper = hl2 + mult * a
    lower = hl2 - mult * a
    fu, fl = upper.copy(), lower.copy()
    direction = np.ones(len(df), dtype=int)
    line = np.full(len(df), np.nan)
    for i in range(1, len(df)):
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        if direction[i - 1] == 1:
            direction[i] = -1 if close[i] < fl[i] else 1
        else:
            direction[i] = 1 if close[i] > fu[i] else -1
        line[i] = fl[i] if direction[i] == 1 else fu[i]
    return pd.Series(direction, index=df.index), pd.Series(line, index=df.index)


def _out(df, long_cond, short_cond, sl_long, sl_short):
    side = np.where(long_cond, 1, np.where(short_cond, -1, 0))
    sl = np.where(side == 1, sl_long, np.where(side == -1, sl_short, np.nan))
    return pd.DataFrame({"side": side, "sl": sl}, index=df.index)


# ---------------------------------------------------------------- estrategias
def ema_pullback(df, tf="15m", htf="1h", fast=20, trend=50, swing=5, tangle=0.003):
    """Método v2: tendencia con EMA50 en el marco mayor, entrada en el retroceso a la EMA20."""
    ohlc = {"open": "first", "high": "max", "low": "min", "close": "last"}
    h = df[["open", "high", "low", "close"]].resample(TF_DELTA[htf]).agg(ohlc).dropna()
    h_ema = ema(h["close"], trend)
    dist = (h["close"] - h_ema) / h_ema
    h_trend = np.where(dist > tangle, 1, np.where(dist < -tangle, -1, 0))
    h_trend = pd.Series(h_trend, index=h.index)
    # Solo se usa la vela del marco mayor ya cerrada.
    h_trend.index = h_trend.index + pd.Timedelta(TF_DELTA[htf])
    close_times = df.index + pd.Timedelta(TF_DELTA[tf])
    tr = h_trend.reindex(close_times, method="ffill").fillna(0).values

    e = ema(df["close"], fast)
    green = df["close"] > df["open"]
    red = df["close"] < df["open"]
    long_c = (tr == 1) & (df["low"] <= e * 1.001) & (df["close"] > e) & green
    short_c = (tr == -1) & (df["high"] >= e * 0.999) & (df["close"] < e) & red
    sl_l = df["low"].rolling(swing).min() * 0.9995
    sl_s = df["high"].rolling(swing).max() * 1.0005
    return _out(df, long_c, short_c, sl_l, sl_s)


def donchian(df, n=20, atr_mult=2.0):
    """Ruptura del canal de Donchian (tortugas) con filtro EMA200."""
    hh = df["high"].shift(1).rolling(n).max()
    ll = df["low"].shift(1).rolling(n).min()
    e200 = ema(df["close"], 200)
    a = atr(df)
    long_c = (df["close"] > hh) & (df["close"] > e200)
    short_c = (df["close"] < ll) & (df["close"] < e200)
    return _out(df, long_c, short_c, df["close"] - atr_mult * a, df["close"] + atr_mult * a)


def rsi2(df, lo=10, hi=90, atr_mult=1.5):
    """Reversión a la media de Connors: RSI(2) extremo a favor de la EMA200."""
    r = rsi(df["close"], 2)
    e200 = ema(df["close"], 200)
    a = atr(df)
    long_c = (df["close"] > e200) & (r < lo)
    short_c = (df["close"] < e200) & (r > hi)
    return _out(df, long_c, short_c, df["close"] - atr_mult * a, df["close"] + atr_mult * a)


def supertrend_flip(df, n=10, mult=3.0):
    """Cambio de dirección del Supertrend; el SL es la línea del Supertrend."""
    d, line = supertrend(df, n, mult)
    flip_up = (d == 1) & (d.shift(1) == -1)
    flip_dn = (d == -1) & (d.shift(1) == 1)
    return _out(df, flip_up, flip_dn, line, line)


def macd_ema200(df, atr_mult=1.5):
    """Cruce del MACD bajo/sobre cero a favor de la EMA200."""
    m = ema(df["close"], 12) - ema(df["close"], 26)
    s = ema(m, 9)
    e200 = ema(df["close"], 200)
    a = atr(df)
    up = (m > s) & (m.shift(1) <= s.shift(1))
    dn = (m < s) & (m.shift(1) >= s.shift(1))
    long_c = up & (m < 0) & (df["close"] > e200)
    short_c = dn & (m > 0) & (df["close"] < e200)
    return _out(df, long_c, short_c, df["close"] - atr_mult * a, df["close"] + atr_mult * a)


# nombre -> (función, RR del TP, descripción corta)
STRATEGIES = {
    "ema_pullback": (ema_pullback, 2.0, "Retroceso a EMA20 a favor de EMA50 del marco mayor (v2)"),
    "donchian": (donchian, 2.0, "Ruptura de Donchian 20 + EMA200, SL 2 ATR"),
    "rsi2": (rsi2, 1.0, "RSI(2) extremo a favor de EMA200, SL 1,5 ATR"),
    "supertrend": (supertrend_flip, 2.0, "Cambio de Supertrend(10,3), SL en la línea"),
    "macd": (macd_ema200, 2.0, "Cruce MACD + EMA200, SL 1,5 ATR"),
}


def run(name, df, tf):
    fn, rr, _ = STRATEGIES[name]
    if name == "ema_pullback":
        htf = {"5m": "1h", "15m": "1h", "30m": "4h", "1h": "4h", "4h": "1d"}[tf]
        sig = fn(df, tf=tf, htf=htf)
    else:
        sig = fn(df)
    sig["rr"] = rr
    return sig
