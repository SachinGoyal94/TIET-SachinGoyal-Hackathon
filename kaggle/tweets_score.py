# Kaggle GPU kernel: score the 16.7k universe stock tweets through the same
# NLP fields as the backfill path (FinBERT sentiment, lexicon event, impact).
#
# Output: /kaggle/working/tweets_scored.csv

import glob
import json
import os
import re
import zipfile

os.environ.setdefault("USE_TF", "0")

import pandas as pd

LABELS = ("Geopolitical", "Macroeconomic", "Credit Event",
          "Merger/Acquisition", "Product Launch", "Other")

BASE_SEVERITY = {"Credit Event": 8.5, "Geopolitical": 5.5, "Macroeconomic": 6.0,
                 "Merger/Acquisition": 6.5, "Product Launch": 7.0, "Other": 6.0}

_LEXICON = {
    "Geopolitical": (r"war", r"invasion", r"sanction", r"tariff", r"embargo",
                     r"missile", r"conflict", r"ceasefire", r"opec",
                     r"chokepoint", r"geopolitic"),
    "Macroeconomic": (r"inflation", r"cpi", r"gdp", r"recession", r"interest rates?",
                      r"rate (hike|cut|pause)", r"fed", r"guidance", r"earnings",
                      r"buyback", r"dividend", r"margins?", r"demand", r"revenue"),
    "Credit Event": (r"downgrade", r"upgrade[sd]?", r"default", r"bankrupt",
                     r"debt", r"bond", r"spreads?", r"covenant", r"refinanc\w+",
                     r"junk", r"liquidity"),
    "Merger/Acquisition": (r"merger", r"acqui\w+", r"takeover", r"bid", r"buyout",
                           r"deal"),
    "Product Launch": (r"launch", r"unveil", r"reveals?", r"rolls out", r"demo",
                       r"new (product|chip|model|app)", r"flagship", r"beta"),
}
_COMPILED = {lab: tuple(re.compile(p, re.IGNORECASE) for p in pats)
             for lab, pats in _LEXICON.items()}


def classify_lexicon(text: str) -> tuple[str, float]:
    votes = {}
    for label, patterns in _COMPILED.items():
        n = sum(1 for p in patterns if p.search(text))
        if n:
            votes[label] = n
    if not votes:
        return "Other", 0.2
    total = sum(votes.values())
    best = max(votes, key=votes.get)
    return best, round(votes[best] / total, 4)


def score_impact(label: str, sentiment: float) -> float:
    base = BASE_SEVERITY.get(label, 6.0)
    ext = min(1.0, abs(sentiment))
    return round(min(10.0, max(1.0, base * (0.75 + 0.5 * ext))), 1)


def main():
    import torch
    from transformers import pipeline

    srcs = glob.glob("/kaggle/input/stock-tweets-universe/*")
    print("mounted:", srcs, flush=True)
    csvs = [s for s in srcs if s.endswith(".csv")]
    if csvs:
        df = pd.read_csv(csvs[0])
    else:
        with zipfile.ZipFile([s for s in srcs if s.endswith(".zip")][0]) as z:
            name = [n for n in z.namelist() if n.endswith(".csv")][0]
            with z.open(name) as f:
                df = pd.read_csv(f)
    print(f"rows: {len(df)}", flush=True)

    clf = pipeline("text-classification", model="ProsusAI/finbert",
                   truncation=True, max_length=128, device=0 if torch.cuda.is_available() else -1)
    texts = df["tweet"].astype(str).tolist()
    results = clf(texts, batch_size=128)
    print("scored", len(results), flush=True)

    sent = []
    for r in results:
        lab = r["label"].lower()
        sent.append(round(r["score"], 4) if lab == "positive"
                    else -round(r["score"], 4) if lab == "negative" else 0.0)

    lc = [classify_lexicon(t) for t in texts]
    df["sentiment"] = sent
    df["event_label"] = [c[0] for c in lc]
    df["event_confidence"] = [c[1] for c in lc]
    df["impact"] = [score_impact(l, s) for l, s in zip(df["event_label"], df["sentiment"])]
    df["external_id"] = [f"tweet-{hash((t, d)) & 0xFFFFFFFFFFFF}"
                         for t, d in zip(df["tweet"], df["date"])]

    out_cols = ["tweet", "ticker", "date", "external_id", "sentiment",
                "event_label", "event_confidence", "impact"]
    df[out_cols].to_csv("/kaggle/working/tweets_scored.csv", index=False)
    print("saved /kaggle/working/tweets_scored.csv", flush=True)
    print("labels:", dict(df["event_label"].value_counts()), flush=True)


if __name__ == "__main__":
    main()
