"""Evaluate a sentiment model against the labeled Kaggle corpus.

Reports accuracy and macro F1 on the full corpus. This is the evidence-pack
number shown on the Key Results slide.

Usage:
    python -m src.scripts.evaluate_sentiment [--model ProsusAI/finbert]
    python -m src.scripts.evaluate_sentiment --model finbert-ft
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import datetime, timezone

from src.engine.config import settings
from src.engine.ingest.seed import load_kaggle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("evaluate")

LABEL_MAP = {"negative": 0, "neutral": 1, "positive": 2}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default=settings.sentiment_model,
                        help="HuggingFace model id, or 'finbert-ft' for the fine-tuned one")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--split", type=str, default="all", choices=["all", "test"],
                        help="'test' scores only the held-out split (same seed as training)")
    args = parser.parse_args()

    model_id = settings.models_dir / "finbert-ft" if args.model == "finbert-ft" else args.model

    rows = load_kaggle(refresh_cache=True)
    if len(rows) < 100:
        raise SystemExit("labeled corpus missing: place all-data.csv in data/seed/")

    if args.split == "test":
        from src.scripts.train_sentiment import stratified_split

        _, rows = stratified_split(rows)
    log.info("corpus: %d rows (split=%s)", len(rows), args.split)

    import numpy as np
    from transformers import pipeline as hf_pipeline

    clf = hf_pipeline("text-classification", model=str(model_id), truncation=True,
                      max_length=64)
    texts = [r["text"] for r in rows]
    preds_raw = clf(texts, batch_size=args.batch_size)
    preds = [LABEL_MAP.get(p["label"].lower(), 1) for p in preds_raw]
    labels = [LABEL_MAP[r["label"]] for r in rows]

    y = np.array(labels)
    yhat = np.array(preds)
    acc = float((yhat == y).mean())
    f1s = []
    for c in range(3):
        tp = int(((yhat == c) & (y == c)).sum())
        fp = int(((yhat == c) & (y != c)).sum())
        fn = int(((yhat != c) & (y == c)).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)

    result = {
        "model": args.model,
        "model_id": str(model_id),
        "rows": len(rows),
        "split": args.split,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(acc, 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "per_class_f1": {k: round(v, 4) for k, v in zip(("negative", "neutral", "positive"), f1s)},
    }
    log.info("result: %s", json.dumps(result, indent=2))

    out = settings.cache_dir / f"sentiment_eval_{args.model.replace('/', '_')}_{args.split}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("saved to %s", out)


if __name__ == "__main__":
    main()
