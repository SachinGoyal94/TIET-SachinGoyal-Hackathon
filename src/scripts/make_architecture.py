"""Generates docs/architecture.png - the high-res architecture diagram.

Run: python -m src.scripts.make_architecture
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")

BG = "#0a1220"
BOX = "#13203a"
EDGE = "#1b2c4d"
TEXT = "#e2e8f0"
SUB = "#94a3b8"
ACCENT = "#2dd4bf"

W, H = 15.5, 10.0

BOXES: dict[str, tuple[float, float, float, float]] = {
    # (x, y, w, h) in axes coords
    "src1": (0.4, 8.45, 2.9, 1.2),
    "src2": (3.5, 8.45, 2.9, 1.2),
    "src3": (6.6, 8.45, 2.9, 1.2),
    "ingest": (1.6, 6.7, 6.4, 1.05),
    "engine": (1.6, 4.6, 6.4, 1.5),
    "db": (3.4, 3.0, 2.8, 1.0),
    "modA": (9.0, 5.4, 2.9, 1.6),
    "modB": (12.2, 5.4, 2.9, 1.6),
    "api": (1.6, 1.55, 6.4, 1.0),
    "ui": (9.0, 1.4, 6.1, 1.75),
}


def box(ax, key, title, lines, edge=EDGE):
    x, y, w, h = BOXES[key]
    rect = plt.Rectangle((x, y), w, h, facecolor=BOX, edgecolor=edge, linewidth=1.6)
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h - 0.30, title, ha="center", va="center",
            fontsize=12.5, fontweight="bold", color=TEXT)
    body = "\n".join(lines)
    ax.text(x + w / 2, y + (h - 0.52) / 2, body, ha="center", va="center",
            fontsize=9.0, color=SUB, linespacing=1.5)


def arrow(ax, x1, y1, x2, y2, color=SUB, label=None, lx=0, ly=0):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, linewidth=1.6))
    if label:
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, ha="center",
                va="center", fontsize=8.6, color=color)


def main() -> None:
    fig, ax = plt.subplots(figsize=(W, H), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 15.5)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(0.4, 9.75, "Financial Risk Intelligence Platform", fontsize=17,
            fontweight="bold", color=TEXT)
    ax.text(0.4, 9.45, "AI/NLP Risk Engine with tactical rebalancing and strategic stress testing",
            fontsize=10.5, color=SUB)

    box(ax, "src1", "GDELT DOC 2.0",
        ["live global news", "15-min updates", "keyless"])
    box(ax, "src2", "Labeled corpora",
        ["Kaggle financial news", "human-labeled", "vendored in /data"])
    box(ax, "src3", "Synthetic feed",
        ["generated headlines", "and social posts", "demo + offline fallback"])

    box(ax, "ingest", "Data Ingestion Layer",
        ["poller + scheduler (APScheduler) · dedupe · source normalization"])

    box(ax, "engine", "AI/NLP RISK ENGINE",
        ["entity matching (aliases, cashtags, sectors)",
         "sentiment: FinBERT  →  [-1.0 .. +1.0]",
         "event classification: zero-shot NLI + finance lexicon",
         "impact score: severity × conviction × corroboration → [1..10]"],
        edge=ACCENT)

    box(ax, "db", "SQLite (WAL)",
        ["articles · signals", "event clusters", "weights · stress runs"])

    box(ax, "modA", "MODULE A",
        ["Tactical index rebalancer",
         "decayed sentiment per ticker",
         "inverse-vol sentiment tilt",
         "cap 20% · turnover 2%"],
        edge=ACCENT)

    box(ax, "modB", "MODULE B",
        ["Strategic stress testing",
         "shock matrix by event type",
         "duration/greeks repricing",
         "Monte Carlo VaR / ES"],
        edge=ACCENT)

    box(ax, "api", "REST API (FastAPI, port 8000)",
        ["/analyze · /signals · /events · /rebalance/* · /stress/* · /portfolio"])

    box(ax, "ui", "React Dashboard",
        ["Overview · Risk Engine · Index Rebalancer · Stress Testing",
         "TypeScript + Tailwind + ECharts, live via TanStack Query"])

    arrow(ax, 1.8, 8.35, 2.6, 7.6)
    arrow(ax, 4.8, 8.35, 4.8, 7.6)
    arrow(ax, 7.8, 8.35, 7.0, 7.6)
    arrow(ax, 4.8, 6.6, 4.8, 6.0)
    arrow(ax, 4.8, 4.55, 4.8, 4.0)
    arrow(ax, 6.2, 3.5, 9.0, 5.6, label="signals", ly=0.18)
    arrow(ax, 6.2, 3.7, 12.2, 5.5, label="events + impact", ly=0.2)
    arrow(ax, 8.0, 2.05, 9.0, 2.05)
    arrow(ax, 10.4, 5.4, 10.4, 3.15, label="weights history", lx=-1.15, ly=0.1)
    arrow(ax, 13.6, 5.4, 13.6, 3.15, label="stress results", lx=0.95, ly=0.1)

    ax.text(7.75, 0.35, "single Docker image · single port · no API keys required",
            ha="center", fontsize=10, color=ACCENT, fontweight="bold")

    out = "docs/architecture.png"
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
