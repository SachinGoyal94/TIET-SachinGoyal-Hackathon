# Kaggle GPU kernel: sentiment model bake-off round 2.
# Evaluates finance-tuned sentiment models on the SAME held-out split
# (stratified, seed 42, 483 rows) used for all prior numbers.
#
# Baseline on this split: ProsusAI/finbert 89.4% / macro F1 0.892
#
# Output: /kaggle/working/bakeoff_round2.json + per-model CSVs

import glob
import json
import random

import numpy as np
import pandas as pd

LABELS = ("positive", "negative", "neutral")


def stratified_test_split(rows, test_ratio=0.1, seed=42):
    by_label = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    rng = random.Random(seed)
    test = []
    for label in sorted(by_label):
        group = by_label[label]
        rng.shuffle(group)
        cut = max(1, int(len(group) * test_ratio))
        test += group[:cut]
    rng.shuffle(test)
    return test


def load_corpus():
    hits = glob.glob("/kaggle/input/**/all-data.csv", recursive=True)
    for path in hits:
        rows = []
        with open(path, encoding="latin-1") as f:
            for line in f:
                parts = line.strip().split(",", 1)
                if len(parts) == 2 and parts[0].strip().lower() in LABELS:
                    rows.append({"text": parts[1].strip().strip('"'),
                                 "label": parts[0].strip().lower()})
        if rows:
            print(f"corpus: {len(rows)} rows from {path}", flush=True)
            return rows
    raise SystemExit("corpus not found")


def macro_f1(preds, labels):
    f1s = []
    for c in LABELS:
        tp = sum(1 for p, l in zip(preds, labels) if p == c and l == c)
        fp = sum(1 for p, l in zip(preds, labels) if p == c and l != c)
        fn = sum(1 for p, l in zip(preds, labels) if p != c and l == c)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return round(sum(f1s) / len(LABELS), 4)


CANDIDATES = [
    "ProsusAI/finbert",
    "StephanAkkerman/FinTwitBERT-sentiment",
    "ahmedrachid/FinancialBERT-Sentiment-Analysis",
    "AnkitAI/FinSense-ModernBERT-Financial-News-Sentiment-Analysis",
]


def normalize(label: str, id2label: dict) -> str:
    lab = label.lower().strip()
    if lab.startswith("label_"):
        try:
            lab = id2label[int(lab.split("_")[-1])].lower()
        except (KeyError, ValueError, IndexError):
            pass
    if lab in LABELS:
        return lab
    for cand in LABELS:
        if cand in lab:
            return cand
    return "neutral"


def main():
    import torch
    from transformers import pipeline

    rows = load_corpus()
    test = stratified_test_split(rows)
    texts = [r["text"] for r in test]
    truth = [r["label"] for r in test]
    print(f"test rows: {len(test)}", flush=True)

    all_results = {}

    for model_id in CANDIDATES:
        print(f"\n=== {model_id} ===", flush=True)
        try:
            clf = pipeline("text-classification", model=model_id,
                           truncation=True, max_length=256,
                           device=0 if torch.cuda.is_available() else -1)
        except Exception as exc:
            print(f"LOAD FAILED: {exc}", flush=True)
            all_results[model_id] = {"error": str(exc)[:200]}
            continue

        id2label = clf.model.config.id2label
        t0 = __import__("time").time()
        raw = clf(texts, batch_size=64)
        elapsed = __import__("time").time() - t0

        preds = [normalize(r["label"], id2label) for r in raw]
        acc = float(np.mean([p == t for p, t in zip(preds, truth)]))
        f1 = macro_f1(preds, truth)
        ms = elapsed / len(texts) * 1000

        all_results[model_id] = {
            "accuracy": round(acc, 4), "macro_f1": f1,
            "ms_per_headline_gpu": round(ms, 1),
        }
        print(f"  accuracy {acc:.4f} | macro F1 {f1}", flush=True)
        pd.DataFrame({"text": texts, "true": truth, "pred": preds}).to_csv(
            f"/kaggle/working/preds_{model_id.replace('/', '_')}.csv", index=False)

        del clf
        torch.cuda.empty_cache()

    summary = {
        "task": "3-way financial headline sentiment",
        "split": "held-out stratified test (seed 42), 483 rows",
        "results": all_results,
        "benchmarks": {"literature_bar_daily_direction": "53-55%", "stocknet_sota": 0.582},
    }
    print(json.dumps(summary, indent=2), flush=True)
    with open("/kaggle/working/bakeoff_round2.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("saved bakeoff_round2.json", flush=True)


if __name__ == "__main__":
    main()
