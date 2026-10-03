"""Benchmark the closed Jev decision model on the same eval rows as the Laya spike.

Reads the saved eval set (identical rows to Laya's eval half), queries the hosted
system-one endpoint, and writes docs/evidence/jev_spike.json.
"""

import json
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT))

LABELS = ("negative", "neutral", "positive")

QUESTION = {
    "sentiment": {
        "type": "choice",
        "instructions": (
            "Classify the investor sentiment of this financial news headline, "
            "from the perspective of the company it discusses."
        ),
        "criteria": {
            "positive": "good news for the company: growth, earnings beats, upgrades, "
                        "successful launches, share gains",
            "negative": "bad news for the company: losses, downgrades, defaults, "
                        "investigations, demand declines, litigation",
            "neutral":  "routine or ambiguous news with no clear investor impact",
        },
    }
}


def main() -> None:
    import numpy as np

    import os

    api_key = os.environ.get("JEV_API_KEY", "")
    base_url = os.environ.get("JEV_BASE_URL", "").rstrip("/")

    rows = json.load(open(ROOT / "data" / "cache" / "laya_out" / "predictions.json",
                          encoding="utf-8"))
    texts = [r["text"] for r in rows]
    y = np.array([0 if r["true"] == "negative" else 1 if r["true"] == "neutral" else 2
                  for r in rows])
    print(f"eval rows: {len(rows)} ({dict(Counter(r['true'] for r in rows))})")

    preds, confs = [], []
    t0 = time.time()
    with httpx.Client(timeout=60.0) as client:
        for i, text in enumerate(texts):
            for attempt in range(5):
                try:
                    resp = client.post(
                        f"{base_url}/systemone",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": "jev", "state": text, "questions": QUESTION},
                    )
                    if resp.status_code == 429 or "rate_limited" in resp.text[:200]:
                        print(f"row {i} rate-limited, waiting 30s")
                        time.sleep(30.0)
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
                    ans = payload["answers"]["sentiment"]
                    choice = str(ans.get("choice", "neutral")).lower()
                    preds.append(LABELS.index(choice) if choice in LABELS else 1)
                    confs.append(float(ans.get("confidence", 0.0)))
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 4:
                        print(f"row {i} failed: {exc}")
                        preds.append(1)
                        confs.append(0.0)
                    else:
                        time.sleep(5.0)
            if (i + 1) % 25 == 0:
                print(f"{i + 1}/{len(texts)} ({time.time() - t0:.0f}s)")
            time.sleep(4.2)  # plan limit: 15 requests/minute
    elapsed = time.time() - t0

    yhat = np.array(preds)
    acc = float((yhat == y).mean())
    f1s = []
    for c in range(3):
        tp = int(((yhat == c) & (y == c)).sum())
        fp = int(((yhat == c) & (y != c)).sum())
        fn = int(((yhat != c) & (y == c)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * r / (p + r) if p + r else 0.0)

    confusion = {}
    for ti, tname in enumerate(LABELS):
        row = {}
        for pi, pname in enumerate(LABELS):
            row[pname] = int(((y == ti) & (yhat == pi)).sum())
        confusion[tname] = row

    metrics = {
        "model": "jev (closed System One decision model, accessed via hosted API)",
        "task": "3-way financial headline sentiment, choice question",
        "rows": len(rows),
        "split": "identical eval rows as the Laya spike (test split, seed 42)",
        "baseline_finbert_base": {"accuracy": 0.8944, "macro_f1": 0.892},
        "laya_zero_shot": {"accuracy": 0.7314, "macro_f1": 0.7176},
        "jev": {
            "accuracy": round(acc, 4),
            "macro_f1": round(float(np.mean(f1s)), 4),
            "per_class_f1": {LABELS[c]: round(f, 4) for c, f in enumerate(f1s)},
            "confusion": confusion,
            "mean_confidence": round(float(np.mean(confs)), 4),
        },
        "latency": {
            "avg_ms_per_decision_incl_network": round(elapsed / len(rows) * 1000, 1),
        },
        "access": "hosted decision API (third-party gateway); not deployable in the "
                  "keyless local submission, benchmarked for evaluation completeness",
    }
    print(json.dumps(metrics, indent=2))
    out = ROOT / "docs" / "evidence" / "jev_spike.json"
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
