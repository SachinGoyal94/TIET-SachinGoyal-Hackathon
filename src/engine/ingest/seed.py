import csv
import logging
import re
from pathlib import Path

from src.engine.config import settings

logger = logging.getLogger(__name__)

KAGGLE_ATTRIBUTION = """\
Dataset: Sentiment Analysis for Financial News
Source: https://www.kaggle.com/datasets/ankurzing/sentiment-analysis-for-financial-news
Original corpus: Malo, P., Sinha, A., Korhonen, P., Wallenius, J., & Takala, P. (2014).
"Good debt or bad debt: A semantic annotation study of financial news headlines."
Journal of the American Society for Information Science and Technology, 65(4).
License: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (as distributed on Kaggle).
Used here, verbatim and with attribution, as a labeled evaluation corpus and
historical demo news. Non-commercial academic use only.
"""

_LABEL_RE = re.compile(r"^(positive|negative|neutral)\s*[,;]\s*(.+)$", re.IGNORECASE)


def load_handmade() -> list[dict]:
    """Rows from our own seed corpus (text, event_label, polarity, ticker)."""
    path = settings.seed_dir / "financial_news_seed.csv"
    if not path.exists():
        logger.warning("handmade seed missing: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return [
            {"text": r["text"].strip(), "event_label": r["event_label"].strip(),
             "polarity": int(r["polarity"]), "ticker": r["ticker"].strip()}
            for r in csv.DictReader(f)
            if r.get("text", "").strip()
        ]


def load_kaggle(refresh_cache: bool = False) -> list[dict]:
    """Labeled headlines from the Kaggle dataset (vendored all-data.csv).

    The raw file is latin-1 with no header; we normalize to UTF-8 once and
    cache the cleaned copy next to it so later runs are fast.
    """
    raw_path = settings.seed_dir / "all-data.csv"
    clean_path = settings.seed_dir / "kaggle_financial_news_clean.csv"

    if clean_path.exists() and not refresh_cache:
        with open(clean_path, encoding="utf-8") as f:
            return [{"text": r["text"], "label": r["label"]} for r in csv.DictReader(f)]

    if not raw_path.exists():
        logger.warning(
            "kaggle corpus not found at %s (backfill continues without it)", raw_path)
        return []

    rows: list[dict] = []
    with open(raw_path, encoding="latin-1") as f:
        for line in f:
            m = _LABEL_RE.match(line.strip())
            if not m:
                continue
            text = m.group(2).strip().strip('"').strip()
            if text:
                rows.append({"text": text, "label": m.group(1).lower()})

    with open(clean_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["text", "label"])
        w.writeheader()
        w.writerows(rows)

    attribution = settings.seed_dir / "ATTRIBUTION.md"
    if not attribution.exists():
        attribution.write_text(KAGGLE_ATTRIBUTION, encoding="utf-8")

    logger.info("kaggle corpus cleaned: %d rows", len(rows))
    return rows
