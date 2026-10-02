import logging
import threading

from src.engine.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _lock:
            if _pipeline is None:
                from transformers import pipeline as hf_pipeline

                logger.info("Loading sentiment model %s", settings.sentiment_model)
                _pipeline = hf_pipeline(
                    "text-classification",
                    model=settings.sentiment_model,
                    truncation=True,
                    max_length=512,
                )
    return _pipeline


def load_model() -> None:
    _get_pipeline()


def is_loaded() -> bool:
    return _pipeline is not None


def score_sentiment(text: str) -> float:
    """Signed sentiment in [-1, 1]: P(positive) - P(negative)."""
    if not text or not text.strip():
        return 0.0
    return _to_score(_get_pipeline()(text)[0])


def score_batch(texts: list[str], batch_size: int = 64) -> list[float]:
    clean = [t if (t and t.strip()) else "neutral." for t in texts]
    return [_to_score(r) for r in _get_pipeline()(clean, batch_size=batch_size)]


def _to_score(result: dict) -> float:
    label, score = result["label"].lower(), float(result["score"])
    if label == "positive":
        return round(score, 4)
    if label == "negative":
        return round(-score, 4)
    return 0.0
