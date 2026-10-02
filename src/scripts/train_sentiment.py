"""Fine-tune the sentiment model on the labeled Kaggle corpus.

Trains ProsusAI/finbert further on the vendored all-data.csv headlines and
saves the result plus eval metrics. Runs fine on CPU (~30-60 min, 8 GB RAM).

Usage:
    python -m src.scripts.train_sentiment [--epochs 3] [--batch-size 16]
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from src.engine.config import settings
from src.engine.ingest.seed import load_kaggle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("train")

LABEL_MAP = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL_MAP.items()}


def stratified_split(rows: list[dict], test_ratio: float = 0.1, seed: int = 42):
    by_label: dict[str, list[dict]] = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    rng = random.Random(seed)
    train, test = [], []
    for label, group in sorted(by_label.items()):
        rng.shuffle(group)
        cut = max(1, int(len(group) * test_ratio))
        test += group[:cut]
        train += group[cut:]
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=64)
    parser.add_argument("--output", type=str, default="finbert-ft")
    args = parser.parse_args()

    import numpy as np
    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    rows = load_kaggle(refresh_cache=True)
    if len(rows) < 100:
        raise SystemExit("labeled corpus missing or too small: place all-data.csv in data/seed/")
    log.info("labeled rows: %d", len(rows))

    train_rows, test_rows = stratified_split(rows)
    log.info("train=%d test=%d", len(train_rows), len(test_rows))

    base = settings.sentiment_model
    tokenizer = AutoTokenizer.from_pretrained(base)

    def tokenize(rows: list[dict]) -> Dataset:
        ds = Dataset.from_dict({
            "text": [r["text"] for r in rows],
            "label": [LABEL_MAP[r["label"]] for r in rows],
        })
        return ds.map(lambda b: tokenizer(b["text"], truncation=True,
                                          max_length=args.max_length), batched=True)

    train_ds, test_ds = tokenize(train_rows), tokenize(test_rows)

    model = AutoModelForSequenceClassification.from_pretrained(
        base, num_labels=3, id2label=ID2LABEL,
        label2id=LABEL_MAP,
    )

    def metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = float((preds == labels).mean())
        f1s = []
        for c in range(3):
            tp = ((preds == c) & (labels == c)).sum()
            fp = ((preds == c) & (labels != c)).sum()
            fn = ((preds != c) & (labels == c)).sum()
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            f1s.append(f1)
        return {"accuracy": acc, "macro_f1": float(np.mean(f1s))}

    out_dir = settings.models_dir / args.output
    targs = TrainingArguments(
        output_dir=str(out_dir / "_ckpt"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="no",
        logging_steps=50,
        use_cpu=not torch.cuda.is_available(),
        report_to=[],
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds,
                      eval_dataset=test_ds, compute_metrics=metrics)
    trainer.train()

    eval_result = trainer.evaluate()
    log.info("eval: %s", eval_result)
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    metrics_out = {
        "model": "finbert-ft",
        "base_model": base,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "epochs": args.epochs,
        "accuracy": round(float(eval_result["eval_accuracy"]), 4),
        "macro_f1": round(float(eval_result["eval_macro_f1"]), 4),
    }
    docs_dir = settings.cache_dir.parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "sentiment_metrics.json").write_text(
        json.dumps(metrics_out, indent=2), encoding="utf-8")
    log.info("saved model to %s and metrics to docs/sentiment_metrics.json", out_dir)


if __name__ == "__main__":
    main()
