import json
import logging
import os
import queue
import threading
from dataclasses import dataclass

from src.engine.config import settings
from src.engine.universe import BY_TICKER

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a financial news analyst. For the given headline, identify each company "
    "or market it discusses and answer for each: sentiment (positive/negative/neutral), "
    "event type (Geopolitical, Macroeconomic, Credit Event, Merger/Acquisition, "
    "Product Launch, Other), and impact band (low/medium/high/severe). "
    'Reply with JSON only: {"entities": [{"name": str, "sentiment": str, '
    '"event_type": str, "impact": str}]}. If no specific company is discussed, '
    "use name \"MARKET\"."
)

FEWSHOT = (
    "<|im_start|>user\nHeadline: Moody's downgrades Boeing to junk status amid cash flow "
    "concerns<|im_end|>\n<|im_start|>assistant\n{\"entities\": [{\"name\": \"Boeing\", "
    "\"sentiment\": \"negative\", \"event_type\": \"Credit Event\", \"impact\": \"severe\"}]}<|im_end|>\n"
    "<|im_start|>user\nHeadline: Oil spikes as conflict escalates while Apple unveils new "
    "chip<|im_end|>\n<|im_start|>assistant\n{\"entities\": [{\"name\": \"MARKET\", "
    "\"sentiment\": \"negative\", \"event_type\": \"Geopolitical\", \"impact\": \"high\"}, "
    "{\"name\": \"Apple\", \"sentiment\": \"positive\", \"event_type\": \"Product Launch\", "
    "\"impact\": \"low\"}]}<|im_end|>\n"
    "<|im_start|>user\nHeadline: Missile strikes halt tanker traffic through key strait, "
    "crude jumps<|im_end|>\n<|im_start|>assistant\n{\"entities\": [{\"name\": \"MARKET\", "
    "\"sentiment\": \"negative\", \"event_type\": \"Geopolitical\", \"impact\": \"severe\"}]}<|im_end|>\n"
    "<|im_start|>user\nHeadline: Apple beats earnings estimates on strong iPhone demand<|im_end|>\n"
    "<|im_start|>assistant\n{\"entities\": [{\"name\": \"Apple\", \"sentiment\": \"positive\", "
    "\"event_type\": \"Macroeconomic\", \"impact\": \"medium\"}]}<|im_end|>\n"
    "<|im_start|>user\nHeadline: Federal Reserve hikes rates 50 basis points warning of more "
    "tightening<|im_end|>\n<|im_start|>assistant\n{\"entities\": [{\"name\": \"MARKET\", "
    "\"sentiment\": \"negative\", \"event_type\": \"Macroeconomic\", \"impact\": \"high\"}]}<|im_end|>\n"
    "<|im_start|>user\nHeadline: Goldman Sachs in advanced talks to acquire boutique asset "
    "manager<|im_end|>\n<|im_start|>assistant\n{\"entities\": [{\"name\": \"Goldman Sachs\", "
    "\"sentiment\": \"positive\", \"event_type\": \"Merger/Acquisition\", \"impact\": \"medium\"}]}<|im_end|>\n"
)


@dataclass(frozen=True)
class EntitySentiment:
    name: str
    sentiment: float
    event_label: str
    impact_band: str


_lock = threading.Lock()
_worker_started = False
_jobs: "queue.Queue[tuple]" = queue.Queue()


def is_configured() -> bool:
    return settings.entity_extractor != "off" and settings.entity_extractor_model.is_file()


def _load_model():
    from llama_cpp import Llama

    logger.info("Loading entity extractor %s", settings.entity_extractor_model.name)
    return Llama(
        model_path=str(settings.entity_extractor_model),
        n_ctx=1024,
        n_threads=max(4, (os.cpu_count() or 8) - 2),
        verbose=False,
    )


def _worker_loop():
    """Single owner thread for the LLM: llama.cpp is not safe for concurrent
    calls on one context, so every extraction job runs serialized here."""
    model = _load_model()
    while True:
        text, magnitude, candidates, out_q = _jobs.get()
        try:
            out_q.put(_run_extraction(model, text, magnitude, candidates))
        except Exception as exc:  # noqa: BLE001 - a bad job must not kill the worker
            logger.warning("extraction job failed: %s", exc)
            out_q.put([])


def _ensure_worker():
    global _worker_started
    with _lock:
        if not _worker_started:
            threading.Thread(target=_worker_loop, name="entity-extractor",
                             daemon=True).start()
            _worker_started = True


def _parse_json(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


_EVENT_LABELS = ("Geopolitical", "Macroeconomic", "Credit Event",
                 "Merger/Acquisition", "Product Launch", "Other")
_DIRECTION = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


def extract(text: str, magnitude: float = 0.5,
            candidates: list[str] | None = None) -> list[EntitySentiment]:
    """Per-entity structured signal for one headline.

    The LLM decides the direction for each entity; ``magnitude`` (typically
    |FinBERT score| of the same headline) supplies the conviction, so the
    returned sentiment is direction_x_magnitude in [-1, 1]. When
    ``candidates`` (alias-matched universe names) are given, the model only
    reports for those companies or MARKET, which kills hallucinated entities.
    Empty list on any failure - callers fall back to the shared score.
    """
    if not text.strip():
        return []
    _ensure_worker()
    out_q: "queue.Queue" = queue.Queue()
    _jobs.put((text, magnitude, candidates, out_q))
    return out_q.get()


def _run_extraction(model, text: str, magnitude: float,
                    candidates: list[str] | None) -> list[EntitySentiment]:
    scope = (f" Only discuss these companies if mentioned: {', '.join(candidates)}. "
             "If none of them or no specific company is discussed, use name \"MARKET\"."
             if candidates else
             'If no specific company is discussed, use name "MARKET".')
    prompt = (FEWSHOT
              + f"<|im_start|>user\nHeadline: {text.strip()}{scope}<|im_end|>\n"
              + "<|im_start|>assistant\n")
    out = model(prompt, max_tokens=200, temperature=0.0,
                stop=["<|im_end|>", "<|im_start|>"])
    payload = _parse_json(out["choices"][0]["text"])
    if not payload or not isinstance(payload.get("entities"), list):
        return []

    results = []
    for ent in payload["entities"][:6]:
        name = str(ent.get("name", "")).strip()
        label = str(ent.get("sentiment", "neutral")).lower()
        if not name or label not in ("positive", "negative", "neutral"):
            continue
        # keep universe companies and the MARKET catch-all; drop the rest
        ticker = next((t for t, c in BY_TICKER.items()
                       if name.lower() in (c.name.lower(), c.ticker.lower())
                       or any(a.lower() == name.lower() for a in c.aliases)), None)
        if ticker is None and name.upper() != "MARKET":
            if candidates and not any(name.lower() == c.lower() for c in candidates):
                continue
        event = next((e for e in _EVENT_LABELS
                      if str(ent.get("event_type", "")).lower() == e.lower()), "Other")
        band = str(ent.get("impact", "low")).lower()
        band = band if band in ("low", "medium", "high", "severe") else "low"
        score = round(_DIRECTION[label] * abs(magnitude), 4)
        results.append(EntitySentiment(name=name, sentiment=score, event_label=event,
                                       impact_band=band))
    return results
