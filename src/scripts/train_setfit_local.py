"""Train the SetFit event classifier locally on CPU (SetFit's home turf).

Light configuration: MiniLM base, ~5.6k class-balanced rows from the
weakly-labeled corpus, 2 epochs. Evaluates on the 380-row hand-labeled gold
set. Usage: python -m src.scripts.train_setfit_local
"""

from __future__ import annotations

import json
import logging
import os
import random

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("HF_HOME", "models")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd

from src.engine.config import REPO_ROOT, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("setfit-local")

LABELS = ("Geopolitical", "Macroeconomic", "Credit Event",
          "Merger/Acquisition", "Product Launch", "Other")

TRAIN_CSV = settings.cache_dir / "kaggle_upload_setfit" / "setfit_train.csv"
GOLD_JSON = REPO_ROOT / "kaggle" / "gold_labels_embedded.json"


def macro_f1(records, key):
    f1s = []
    for c in LABELS:
        tp = sum(1 for r in records if r[key] == c and r["true"] == c)
        fp = sum(1 for r in records if r[key] == c and r["true"] != c)
        fn = sum(1 for r in records if r[key] != c and r["true"] == c)
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * rc / (p + rc) if p + rc else 0.0)
    return round(sum(f1s) / 3, 4)


def main() -> None:
    from datasets import Dataset
    from setfit import SetFitModel, Trainer, TrainingArguments

    df = pd.read_csv(TRAIN_CSV)
    log.info("corpus rows: %d", len(df))

    rng = random.Random(42)
    per_class = 25  # SetFit few-shot sweet spot; pairing grows quadratically
    parts = []
    for lab in LABELS:
        sub = df[df["label"] == lab].to_dict("records")
        if len(sub) >= per_class:
            parts.extend(rng.sample(sub, per_class))
        else:
            parts.extend(sub * (per_class // max(len(sub), 1)) + sub)
    train_df = pd.DataFrame(parts)
    log.info("balanced training rows: %d", len(train_df))

    model = SetFitModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
    args = TrainingArguments(
        batch_size=16,
        num_epochs=2,
        body_learning_rate=2e-5,
        head_learning_rate=1e-2,
        report_to=[],
        show_progress_bar=True,
    )
    train_ds = Dataset.from_dict({
        "text": train_df["title"].astype(str).tolist(),
        "label": [LABELS.index(l) for l in train_df["label"]],
    })
    trainer = Trainer(model=model, args=args, train_dataset=train_ds)
    trainer.train()

    gold = json.load(open(GOLD_JSON, encoding="utf-8"))
    log.info("evaluating on %d gold headlines...", len(gold))
    records = []
    for row in gold:
        pred = model.predict([row["title"]])[0]
        records.append({"title": row["title"], "true": row["hand_label"],
                        "setfit": LABELS[pred]})

    agree = sum(1 for r in records if r["setfit"] == r["true"])
    metrics = {
        "task": "6-label event classification on hand-labeled gold (380 headlines)",
        "training": "SetFit (all-MiniLM-L6-v2, local CPU) on ~5.6k class-balanced "
                    "pipeline-labeled headlines (weak labels, gold excluded)",
        "setfit_local": {
            "accuracy": round(agree / len(records), 4),
            "macro_f1": macro_f1(records, "setfit"),
        },
        "pipeline_baseline": {
            "accuracy": 0.592,
            "note": "the deployed pipeline's agreement with the same gold set",
        },
    }
    log.info("metrics: %s", json.dumps(metrics, indent=2))

    out_dir = settings.models_dir / "event_classifier"
    model.save_pretrained(str(out_dir))
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    (settings.cache_dir / "setfit_local_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8")
    (settings.cache_dir / "setfit_local_predictions.json").write_text(
        json.dumps(records, indent=1), encoding="utf-8")
    log.info("saved model to %s and metrics to data/cache/setfit_local_metrics.json", out_dir)


if __name__ == "__main__":
    main()
