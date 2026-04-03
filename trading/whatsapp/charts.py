from __future__ import annotations
import io
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

if TYPE_CHECKING:
    from broker.models import Bar, Position

plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor": "#16213e",
    "axes.edgecolor": "#e94560",
    "axes.labelcolor": "#eee",
    "text.color": "#eee",
    "xtick.color": "#aaa",
    "ytick.color": "#aaa",
    "grid.color": "#333",
    "grid.alpha": 0.3,
})

FIGSIZE = (8, 6)
DPI = 100


def render_price_chart(symbol: str, bars: list[Bar]) -> bytes:
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    if not bars:
        ax.text(0.5, 0.5, f"No data for {symbol}", ha="center", va="center", fontsize=16)
        ax.set_axis_off()
    else:
        dates = [b.timestamp for b in bars]
        closes = [float(b.close) for b in bars]
        volumes = [b.volume for b in bars]

        ax.plot(dates, closes, color="#e94560", linewidth=2, label="Close")
        ax.fill_between(dates, closes, alpha=0.1, color="#e94560")
        ax.set_ylabel("Price ($)")
        ax.legend(loc="upper left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.grid(True)

        if volumes and any(v > 0 for v in volumes):
            ax2 = ax.twinx()
            ax2.bar(dates, volumes, alpha=0.2, color="#0f3460", width=0.8)
            ax2.set_ylabel("Volume")
            ax2.tick_params(axis="y", colors="#666")

    ax.set_title(f"{symbol} Price Chart", fontsize=14, fontweight="bold")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_portfolio_chart(positions: list[Position]) -> bytes:
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    if not positions:
        ax.text(0.5, 0.5, "No positions", ha="center", va="center", fontsize=16)
        ax.set_axis_off()
    else:
        labels = [p.symbol.ticker for p in positions]
        values = [float(p.market_value) for p in positions]
        colors = plt.cm.Set2.colors[:len(labels)]

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%",
            colors=colors, textprops={"fontsize": 11},
        )
        for t in autotexts:
            t.set_fontsize(10)

    ax.set_title("Portfolio Allocation", fontsize=14, fontweight="bold")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
