# Kaggle GPU kernel: fine-tunes FinBERT on the labeled financial news corpus.
# Attach dataset: ankurzing/sentiment-analysis-for-financial-news
# Push with:     kaggle kernels push -p kaggle/
# Output:        /kaggle/working/finbert-ft/ (model) + metrics.json

import glob
import json
import random

import numpy as np
import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

BASE = "ProsusAI/finbert"
LABEL_MAP = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL_MAP.items()}


def load_rows():
    import csv

    candidates = glob.glob("/kaggle/input/**/all-data.csv", recursive=True)
    print("input candidates:", candidates)
    for path in candidates:
        with open(path, encoding="latin-1") as f:
            rows = []
            for line in f:
                parts = line.strip().split(",", 1)
                if len(parts) == 2 and parts[0].strip().lower() in LABEL_MAP:
                    rows.append({"text": parts[1].strip().strip('"'), "label": parts[0].strip().lower()})
            print(f"loaded {len(rows)} rows from {path}")
            if rows:
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
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def main():
    rows = load_rows()
    train_rows, test_rows = stratified_split(rows)
    print(f"train={len(train_rows)} test={len(test_rows)}")

    tokenizer = AutoTokenizer.from_pretrained(BASE)

    def tokenize(rows):
        ds = __import__("datasets").Dataset.from_dict({
            "text": [r["text"] for r in rows],
            "label": [LABEL_MAP[r["label"]] for r in rows],
        })
        return ds.map(lambda b: tokenizer(b["text"], truncation=True, max_length=64), batched=True)

    train_ds, test_ds = tokenize(train_rows), tokenize(test_rows)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE, num_labels=3, id2label=ID2LABEL, label2id=LABEL_MAP)

    def metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = float((preds == labels).mean())
        f1s = []
        for c in range(3):
            tp = ((preds == c) & (labels == c)).sum()
            fp = ((preds == c) & (labels != c)).sum()
            fn = ((preds != c) & (labels == c)).sum()
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else 0.0
            f1s.append(2 * p * r / (p + r) if p + r else 0.0)
        return {"accuracy": acc, "macro_f1": float(np.mean(f1s))}

    args = TrainingArguments(
        output_dir="/kaggle/working/ckpt",
        num_train_epochs=3,
        per_device_train_batch_size=32,
        per_device_eval_batch_size=64,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="no",
        logging_steps=50,
        report_to=[],
        fp16=torch.cuda.is_available(),
    )
    trainer = Trainer(model=model, args=args, train_dataset=train_ds,
                      eval_dataset=test_ds, compute_metrics=metrics,
                      data_collator=DataCollatorWithPadding(tokenizer))
    trainer.train()

    eval_result = trainer.evaluate()
    print("EVAL:", json.dumps(eval_result))
    trainer.save_model("/kaggle/working/finbert-ft")
    tokenizer.save_pretrained("/kaggle/working/finbert-ft")

    metrics = {
        "model": "finbert-ft",
        "base_model": BASE,
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "accuracy": round(float(eval_result["eval_accuracy"]), 4),
        "macro_f1": round(float(eval_result["eval_macro_f1"]), 4),
    }
    with open("/kaggle/working/metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print("METRICS:", json.dumps(metrics))


if __name__ == "__main__":
    main()
