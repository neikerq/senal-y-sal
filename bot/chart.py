"""Gráfico de velas estilo Binance (tema oscuro) para cada señal."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BG = "#181A20"
GRID = "#2B3139"
TEXT = "#848E9C"
WHITE = "#EAECEF"
GREEN = "#0ECB81"
RED = "#F6465D"
YELLOW = "#F0B90B"


def _fmt(p):
    d = 2 if p >= 1000 else 3 if p >= 10 else 4 if p >= 1 else 5 if p >= 0.01 else 7
    return f"{p:.{d}f}"


def render(df, st_dir, st_line, side, entry, sl, tp, title, path,
           tz="America/Caracas", bars=90, signal_idx=None):
    """df: velas (índice UTC); st_dir/st_line: Supertrend alineado con df.
    signal_idx: posición de la vela de la señal dentro de df (por defecto la última)."""
    if signal_idx is None:
        signal_idx = len(df) - 1
    start = max(0, signal_idx - bars + 1)
    end = min(len(df), signal_idx + 1 + 12)  # unas velas después, si existen
    d = df.iloc[start:end]
    sd = st_dir.iloc[start:end].values
    sline = st_line.iloc[start:end].values
    n = len(d)
    x = np.arange(n)
    sx = signal_idx - start
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    up = c >= o
    col = np.where(up, GREEN, RED)

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=130)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # zonas de TP y SL desde la vela de la señal
    right = n + 6
    ax.fill_between([sx, right], entry, tp, color=GREEN, alpha=0.10, lw=0)
    ax.fill_between([sx, right], entry, sl, color=RED, alpha=0.10, lw=0)

    # velas
    ax.vlines(x, l, h, color=col, lw=1)
    body_lo = np.minimum(o, c)
    body_h = np.maximum(np.abs(c - o), (h.max() - l.min()) * 0.0015)
    ax.bar(x, body_h, bottom=body_lo, width=0.62, color=col, lw=0)

    # Supertrend
    for val, color in ((1, GREEN), (-1, RED)):
        y = np.where(sd == val, sline, np.nan)
        ax.plot(x, y, color=color, lw=1.6, alpha=0.9)

    # niveles
    for y, color, label, ls in (
        (tp, GREEN, "TP", "--"),
        (entry, YELLOW, "Entrada", "-"),
        (sl, RED, "SL", "--"),
    ):
        ax.hlines(y, sx, right, color=color, lw=1.2, ls=ls)
        ax.text(right + 0.3, y, f" {label} {_fmt(y)} ", color=BG, fontsize=8.5,
                fontweight="bold", va="center", ha="left",
                bbox=dict(boxstyle="square,pad=0.25", fc=color, ec="none"))

    # flecha de la señal
    span = h.max() - l.min()
    if side == 1:
        ax.annotate("", xy=(sx, l[sx] - span * 0.01), xytext=(sx, l[sx] - span * 0.08),
                    arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=2))
    else:
        ax.annotate("", xy=(sx, h[sx] + span * 0.01), xytext=(sx, h[sx] + span * 0.08),
                    arrowprops=dict(arrowstyle="-|>", color=RED, lw=2))

    # ejes
    lo = min(l.min(), sl, tp) - span * 0.06
    hi = max(h.max(), sl, tp) + span * 0.06
    ax.set_ylim(lo, hi)
    ax.set_xlim(-1, right + 9)
    ax.yaxis.tick_right()
    ax.tick_params(colors=TEXT, labelsize=8, length=0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _fmt(v)))
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(color=GRID, lw=0.6)
    ticks = x[max(1, n // 16):: max(1, n // 8)]
    times = d.index.tz_convert(tz)
    ax.set_xticks(ticks)
    ax.set_xticklabels([times[i].strftime("%d/%m %H:%M") for i in ticks])

    # precio actual (última vela)
    last = c[-1]
    ax.text(1.0, last, f" {_fmt(last)} ", transform=ax.get_yaxis_transform(),
            color=WHITE, fontsize=8, va="center", ha="left",
            bbox=dict(boxstyle="square,pad=0.2", fc=GREEN if up[-1] else RED, ec="none"))

    fig.text(0.015, 0.965, title, color=WHITE, fontsize=12, fontweight="bold", va="top")
    fig.text(0.015, 0.915, "Supertrend(10, 3) · velas cerradas · hora de Caracas",
             color=TEXT, fontsize=8.5, va="top")
    fig.subplots_adjust(left=0.02, right=0.9, top=0.86, bottom=0.08)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path
