# Kaggle spike: benchmark Laya (421M decision encoder) against FinBERT on the
# labeled financial-news corpus. Attach dataset:
#   ankurzing/sentiment-analysis-for-financial-news
# Baseline to beat (same 483-row test split, seed 42):
#   FinBERT base:      accuracy 0.8944, macro F1 0.892
#   FinBERT fine-tune: accuracy 0.8903, macro F1 0.880

import glob
import json
import os
import random
import subprocess
import sys
import time

os.environ["USE_TF"] = "0"
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "laya"], check=True)

LABEL_MAP = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {0: "negative", 1: "neutral", 2: "positive"}

SENTIMENT_QUESTION = {
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


def load_rows():
    candidates = glob.glob("/kaggle/input/**/all-data.csv", recursive=True)
    print("input candidates:", candidates)
    for path in candidates:
        rows = []
        with open(path, encoding="latin-1") as f:
            for line in f:
                parts = line.strip().split(",", 1)
                if len(parts) == 2 and parts[0].strip().lower() in LABEL_MAP:
                    rows.append({"text": parts[1].strip().strip('"'),
                                 "label": parts[0].strip().lower()})
        if rows:
            print(f"loaded {len(rows)} rows from {path}")
            return rows
    raise SystemExit("dataset not found")


def stratified_split(rows, test_ratio=0.1, seed=42):
    by_label = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    rng = random.Random(seed)
    train, test = [], []
    for label in sorted(by_label):
        group = by_label[label]
        rng.shuffle(group)
        cut = max(1, int(len(group) * test_ratio))
        test += group[:cut]
        train += group[cut:]
    rng.shuffle(test)
    return test


def main():
    import numpy as np

    test_rows = stratified_split(load_rows())
    # calibration half for temperature fitting, eval half untouched (HF blog guidance:
    # recalibrate on held-out data, never on the final test set)
    cal_rows, eval_rows = test_rows[: len(test_rows) // 2], test_rows[len(test_rows) // 2 :]
    print(f"calibration rows: {len(cal_rows)}, eval rows: {len(eval_rows)}")

    from laya import Router

    router = Router()

    def run(rows, tag):
        t0 = time.time()
        preds, confs = [], []
        for i, row in enumerate(rows):
            result = router.predict(row["text"], SENTIMENT_QUESTION)
            ans = result["answers"]["sentiment"]
            choice = str(ans.get("choice", "neutral")).lower()
            if choice not in LABEL_MAP:
                choice = "neutral"
            preds.append(LABEL_MAP[choice])
            confs.append(float(ans.get("confidence", 0.0)))
            if (i + 1) % 100 == 0:
                print(f"{tag} {i + 1}/{len(rows)} ({time.time() - t0:.0f}s)")
        return preds, confs, time.time() - t0

    cal_preds, cal_confs, _ = run(cal_rows, "cal")
    eval_preds, eval_confs, elapsed = run(eval_rows, "eval")

    # temperature scaling on the calibration half (single-parameter fit)
    def nll_for_temperature(logits: np.ndarray, labels: np.ndarray, temp: float) -> float:
        scaled = logits / temp
        scaled -= scaled.max(axis=1, keepdims=True)
        logp = scaled - np.log(np.exp(scaled).sum(axis=1, keepdims=True))
        return -logp[np.arange(len(labels)), labels].mean()

    def conf_to_logits(conf: float, n_classes: int = 3) -> np.ndarray:
        p_top = min(max(conf, 1e-6), 1 - 1e-6)
        rest = (1 - p_top) / (n_classes - 1)
        probs = np.array([rest, rest, rest])
        probs[0] = p_top
        return np.log(probs)

    best_t, best_loss = 1.0, None
    cal_logits = np.array([conf_to_logits(c) for c in cal_confs])
    cal_labels = np.array([LABEL_MAP[r["label"]] for r in cal_rows])
    for temp in np.arange(0.5, 4.01, 0.1):
        loss = nll_for_temperature(cal_logits, cal_labels, float(temp))
        if best_loss is None or loss < best_loss:
            best_t, best_loss = float(temp), loss

    eval_logits = np.array([conf_to_logits(c) for c in eval_confs])
    scaled = eval_logits / best_t
    scaled -= scaled.max(axis=1, keepdims=True)
    cal_probs = np.exp(scaled) / np.exp(scaled).sum(axis=1, keepdims=True)

    def ece(probs: np.ndarray, preds: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
        conf = probs.max(axis=1)
        correct = (preds == labels).astype(float)
        total = 0.0
        for b in range(bins):
            lo, hi = b / bins, (b + 1) / bins
            mask = (conf > lo) & (conf <= hi)
            if mask.sum() == 0:
                continue
            total += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
        return float(total)

    y = np.array([LABEL_MAP[r["label"]] for r in eval_rows])
    yhat = np.array(eval_preds)
    acc = float((yhat == y).mean())
    f1s = []
    for c in range(3):
        tp = int(((yhat == c) & (y == c)).sum())
        fp = int(((yhat == c) & (y != c)).sum())
        fn = int(((yhat != c) & (y == c)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * r / (p + r) if p + r else 0.0)

    # selective accuracy: error rate at 70% automated coverage
    conf_eval = eval_probs_max = cal_probs.max(axis=1)
    order = np.argsort(-conf_eval)
    k70 = max(1, int(0.7 * len(y)))
    sel_acc = float((yhat[order[:k70]] == y[order[:k70]]).mean())

    confusion = {}
    for true_label in ID2LABEL.values():
        row = {}
        for pred_label in ID2LABEL.values():
            row[pred_label] = int(((y == LABEL_MAP[true_label]) & (yhat == LABEL_MAP[pred_label])).sum())
        confusion[true_label] = row

    metrics = {
        "model": "laya (convaiinnovations/laya, 421M ModernBERT decision encoder)",
        "task": "3-way financial headline sentiment, choice question",
        "rows": len(eval_rows),
        "split": "test split (stratified, seed 42) — identical to FinBERT baseline; "
                 "half used for temperature fit, half for eval",
        "baseline_finbert_base": {"accuracy": 0.8944, "macro_f1": 0.892, "rows": 483},
        "laya": {
            "accuracy": round(acc, 4),
            "macro_f1": round(float(np.mean(f1s)), 4),
            "per_class_f1": {ID2LABEL[c]: round(f, 4) for c, f in enumerate(f1s)},
            "confusion": confusion,
            "temperature_fit": round(best_t, 2),
            "ece_after_scaling": round(ece(cal_probs, yhat, y), 4),
            "selective_accuracy_at_70pct_coverage": round(sel_acc, 4),
        },
        "latency": {
            "gpu_ms_per_decision": round(elapsed / len(eval_rows) * 1000, 1),
        },
    }
    print(json.dumps(metrics, indent=2))
    with open("/kaggle/working/metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    with open("/kaggle/working/predictions.json", "w") as f:
        json.dump([
            {"text": r["text"], "true": r["label"], "pred": ID2LABEL[p], "conf": round(c, 4)}
            for r, p, c in zip(eval_rows, eval_preds, eval_confs)
        ], f, indent=1)

    # CPU latency on a 50-row subset (the deployment environment for the demo)
    cpu_code = r"""
import json, random, glob, time
LABEL_MAP = {"negative": 0, "neutral": 1, "positive": 2}
def load_rows():
    for path in glob.glob("/kaggle/input/**/all-data.csv", recursive=True):
        rows = []
        with open(path, encoding="latin-1") as f:
            for line in f:
                parts = line.strip().split(",", 1)
                if len(parts) == 2 and parts[0].strip().lower() in LABEL_MAP:
                    rows.append(parts[1].strip().strip('"'))
        if rows:
            return rows
rows = load_rows()
random.Random(42).shuffle(rows)
from laya import Router
router = Router()
q = {"s": {"type": "choice", "instructions": "sentiment?",
           "criteria": {"positive": "good for company", "negative": "bad for company", "neutral": "unclear"}}}
for _ in range(3):
    router.predict(rows[0], q)
t0 = time.time()
n = 50
for text in rows[:n]:
    router.predict(text, q)
per_ms = (time.time() - t0) / n * 1000
with open("/kaggle/working/cpu_latency.json", "w") as f:
    json.dump({"cpu_ms_per_decision": round(per_ms, 1), "rows": n}, f)
print("CPU ms/decision:", round(per_ms, 1))
"""
    try:
        out = subprocess.run(
            ["python", "-c", cpu_code], capture_output=True, text=True,
            timeout=600, env={"CUDA_VISIBLE_DEVICES": "", "PATH": "/usr/bin:/usr/local/bin:/opt/conda/bin",
                              "HOME": "/root", "PYTHONPATH": "/opt/conda/lib/python3.13/site-packages"})
        print(out.stdout[-500:])
        if out.returncode != 0:
            print("CPU probe failed:", out.stderr[-400:])
    except Exception as exc:
        print("CPU probe skipped:", exc)


if __name__ == "__main__":
    main()
