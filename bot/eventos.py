"""Lista los movimientos bruscos de los últimos N días (velas diarias)."""
import argparse

import pandas as pd

from . import data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--symbols", nargs="+",
                    default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "BNBUSDT"])
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    rets = {}
    for s in a.symbols:
        d = data.history(s, "1d", a.days)
        rets[s] = (d["close"] / d["close"].shift(1) - 1) * 100
        # rango intradía (máximo vs mínimo) para detectar desplomes con rebote
        rets[s + "_rango"] = (d["high"] / d["low"] - 1) * 100
    df = pd.DataFrame(rets).dropna()
    alts = [s for s in a.symbols if s != "BTCUSDT"]
    df["alts_prom"] = df[alts].mean(axis=1)
    df["score"] = df["BTCUSDT"].abs() + df["alts_prom"].abs()
    top = df.sort_values("score", ascending=False).head(a.top).sort_index()
    cols = ["BTCUSDT", "alts_prom"] + alts + ["BTCUSDT_rango"]
    out = top[cols].round(1)
    out.index = out.index.strftime("%Y-%m-%d")
    print("# Días con movimientos más bruscos (cierre vs cierre, %, UTC)")
    print(out.to_markdown())
    # caídas/subidas intradía extremas aunque el cierre no lo muestre
    wick = df.sort_values("BTCUSDT_rango", ascending=False).head(10)[["BTCUSDT", "BTCUSDT_rango", "alts_prom"]].round(1)
    wick.index = wick.index.strftime("%Y-%m-%d")
    print("\n# Días con mayor rango intradía de BTC (%)")
    print(wick.to_markdown())


if __name__ == "__main__":
    main()
