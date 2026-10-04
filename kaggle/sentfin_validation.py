# Kaggle GPU kernel: per-entity sentiment validation on SEntFiN 1.0.
# Compares the platform's per-entity extraction (Qwen3-4B, JSON output)
# against a FinBERT headline-level baseline. Eval set: 400 multi-entity
# headlines (907 entity judgments), fixed sample (seed 42) from
# sentfin_sample.json (uploaded alongside this script).

import glob
import json
import os
import re

import pandas as pd
import torch

_here = "/kaggle/input/sentfin-sample"
_candidates = glob.glob(os.path.join(_here, "**", "sentfin_sample.json"), recursive=True)
DATA = json.load(open(_candidates[0], encoding="utf-8"))
print(f"eval set: {len(DATA)} rows", flush=True)

SYSTEM = (
    "You are a financial news analyst. For the given headline, identify each company "
    "or market it discusses and answer for each: sentiment (positive/negative/neutral). "
    'Reply with JSON only: {"entities": [{"name": str, "sentiment": str}]}.'
)


def extract(headline: str, candidates: list[str]) -> dict[str, str]:
    scope = (" Only discuss these companies if mentioned: " + ", ".join(candidates)
             + '. If none is discussed, use name "MARKET".')
    prompt = (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
              f"<|im_start|>user\nHeadline: {headline}{scope}<|im_end|>\n"
              f"<|im_start|>assistant\n{{")
    ids = tok(prompt, return_tensors="pt").to(model_obj.device)
    gen = model_obj.generate(**ids, max_new_tokens=160, do_sample=False)
    text = tok.decode(gen[0][ids["input_ids"].shape[1]:])
    text = "{" + text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        payload = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    result = {}
    for ent in payload.get("entities", [])[:8]:
        name = str(ent.get("name", "")).strip().lower()
        sent = str(ent.get("sentiment", "")).lower()
        if name and sent in ("positive", "negative", "neutral"):
            result[name] = sent
    return result


def macro_f1(records, key):
    f1s = []
    for c in ("positive", "negative", "neutral"):
        tp = sum(1 for r in records if r[key] == c and r["true"] == c)
        fp = sum(1 for r in records if r[key] == c and r["true"] != c)
        fn = sum(1 for r in records if r[key] != c and r["true"] == c)
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * rc / (p + rc) if p + rc else 0.0)
    return round(sum(f1s) / 3, 4)


def main():
    global tok, model_obj
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

    model_id = "Qwen/Qwen3-4B-Instruct-2507"
    tok = AutoTokenizer.from_pretrained(model_id)
    model_obj = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.bfloat16, device_map="cuda:0")

    finbert = pipeline("text-classification", model="ProsusAI/finbert",
                       truncation=True, max_length=128, device=0)

    llm_hits = fb_hits = total = 0
    records = []
    for i, row in enumerate(DATA):
        truth = {k.lower().strip(): v for k, v in row["decisions"].items()}
        headline = row["title"]
        try:
            pred = extract(headline, list(truth.keys()))
        except Exception as exc:
            print(f"row {i} extract failed: {exc}", flush=True)
            pred = {}
        fb = finbert(headline)[0]["label"].lower()
        for name, true_sent in truth.items():
            total += 1
            pred_sent = None
            for pname, psent in pred.items():
                if pname in name or name in pname:
                    pred_sent = psent
                    break
            if pred_sent == true_sent:
                llm_hits += 1
            if fb == true_sent:
                fb_hits += 1
            records.append({"headline": headline, "entity": name,
                            "true": true_sent, "llm": pred_sent, "finbert": fb})
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(DATA)} llm={llm_hits / total:.3f} "
                  f"fb={fb_hits / total:.3f}", flush=True)

    metrics = {
        "task": "per-entity sentiment on SEntFiN 1.0 multi-entity headlines",
        "rows": len(DATA),
        "entity_judgments": total,
        "per_entity_llm": {
            "accuracy": round(llm_hits / total, 4),
            "macro_f1": macro_f1(records, "llm"),
        },
        "finbert_headline_baseline": {
            "accuracy": round(fb_hits / total, 4),
            "macro_f1": macro_f1(records, "finbert"),
            "note": "one shared headline label applied to every entity - the "
                    "approach the per-entity layer replaces",
        },
    }
    print(json.dumps(metrics, indent=2), flush=True)
    with open("/kaggle/working/per_entity_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    pd.DataFrame(records).to_csv("/kaggle/working/per_entity_predictions.csv",
                                 index=False)
    print("saved outputs", flush=True)


if __name__ == "__main__":
    main()
