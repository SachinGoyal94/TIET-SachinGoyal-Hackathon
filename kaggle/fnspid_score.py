# Kaggle GPU kernel: score the 91k FNSPID universe headlines through the same
# NLP fields the platform's backfill path uses (FinBERT sentiment, lexicon
# event classification, composite impact), at T4 speed.
#
# Output: /kaggle/working/fnspid_scored.csv
#         text, ticker, date, external_id, sentiment, event_label,
#         event_confidence, impact

import glob
import json
import os
import re

os.environ.setdefault("USE_TF", "0")

import pandas as pd

LABELS = ("Geopolitical", "Macroeconomic", "Credit Event",
          "Merger/Acquisition", "Product Launch", "Other")

BASE_SEVERITY = {"Credit Event": 8.5, "Geopolitical": 8.0, "Macroeconomic": 7.0,
                 "Merger/Acquisition": 6.0, "Product Launch": 3.5, "Other": 3.0}

_LEXICON = {
    "Geopolitical": (r"war", r"invasion", r"sanction", r"tariff", r"embargo",
                     r"missile", r"conflict", r"ceasefire", r"opec",
                     r"trade (war|dispute|deal|pact)", r"export (control|ban)",
                     r"chokepoint", r"shipping lane", r"geopolitic"),
    "Macroeconomic": (r"inflation", r"cpi", r"gdp", r"recession", r"interest rates?",
                      r"rate (hike|cut|pause)", r"central bank", r"federal reserve",
                      r"treasury yields?", r"unemployment", r"guidance", r"earnings",
                      r"quarterly results?", r"buyback", r"dividend", r"margins?",
                      r"demand", r"revenue"),
    "Credit Event": (r"downgrade", r"upgrade[sd]?", r"default", r"bankrupt",
                     r"chapter 11", r"debt", r"bond",
                     r"credit (rating|spread|curve)", r"covenant", r"refinanc\w+",
                     r"moody'?s?", r"fitch", r"junk status", r"liquidity crisis"),
    "Merger/Acquisition": (r"merger", r"acqui\w+", r"takeover", r"bid", r"buyout",
                           r"deal talks", r"antitrust probe"),
    "Product Launch": (r"launch", r"unveil", r"reveals?", r"rolls out", r"roll back",
                       r"new (product|platform|chip|model|suite|line|app)",
                       r"pilots?", r"beta", r"flagship", r"next-generation"),
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
    base = BASE_SEVERITY.get(label, 3.0)
    ext = min(1.0, abs(sentiment))
    return round(min(10.0, max(1.0, base * (0.75 + 0.5 * ext))), 1)


def main():
    import torch
    from transformers import pipeline

    import zipfile

    srcs = glob.glob("/kaggle/input/fnspid-universe-headlines/*")
    import glob as _g
    print("input listing:", _g.glob("/kaggle/input/**/*"), flush=True)
    print("mounted inputs:", srcs, flush=True)
    csvs = [s for s in srcs if s.endswith(".csv")]
    if csvs:
        src = csvs[0]
        df = pd.read_csv(src)
    else:
        zips = [s for s in srcs if s.endswith(".zip")]
        with zipfile.ZipFile(zips[0]) as z:
            name = [n for n in z.namelist() if n.endswith(".csv")][0]
            with z.open(name) as f:
                df = pd.read_csv(f)
    print(f"rows: {len(df)}", flush=True)

    clf = pipeline("text-classification", model="ProsusAI/finbert",
                   truncation=True, max_length=128, device=0 if torch.cuda.is_available() else -1)
    texts = df["title"].astype(str).tolist()
    print("scoring...", flush=True)
    results = clf(texts, batch_size=128)
    print("scored", len(results), flush=True)

    sent = []
    for r in results:
        lab = r["label"].lower()
        sent.append(round(r["score"], 4) if lab == "positive"
                    else -round(r["score"], 4) if lab == "negative" else 0.0)

    labels_confs = [classify_lexicon(t) for t in texts]
    df["sentiment"] = sent
    df["event_label"] = [c[0] for c in labels_confs]
    df["event_confidence"] = [c[1] for c in labels_confs]
    df["impact"] = [score_impact(l, s) for l, s in zip(df["event_label"], df["sentiment"])]
    df["external_id"] = [f"fnspid-{hash((t, d)) & 0xFFFFFFFFFFFF}"
                         for t, d in zip(df["title"], df["date"])]

    out_cols = ["title", "ticker", "date", "external_id", "sentiment",
                "event_label", "event_confidence", "impact"]
    df[out_cols].to_csv("/kaggle/working/fnspid_scored.csv", index=False)
    print("saved /kaggle/working/fnspid_scored.csv", flush=True)
    print(json.dumps(dict(df["event_label"].value_counts()), indent=2), flush=True)


if __name__ == "__main__":
    main()
