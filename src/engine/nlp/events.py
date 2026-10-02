import logging
import re
import threading
from dataclasses import dataclass, field

from src.engine.config import settings

logger = logging.getLogger(__name__)

EVENT_LABELS: tuple[str, ...] = (
    "Geopolitical",
    "Macroeconomic",
    "Credit Event",
    "Merger/Acquisition",
    "Product Launch",
    "Other",
)

_HYPOTHESIS = "This headline is about {}."

_ZS_TEMPLATE = {
    "Geopolitical": "a geopolitical event such as war, sanctions, tariffs, conflict or trade disputes",
    "Macroeconomic": "a macroeconomic event such as earnings, growth, inflation, interest rates or the economy",
    "Credit Event": "a credit event such as debt default, downgrade, bankruptcy or credit ratings",
    "Merger/Acquisition": "a merger or acquisition deal between companies",
    "Product Launch": "a product launch or announcement of a new product",
    "Other": "a routine corporate or administrative matter",
}

# finance-specific keyword votes, one regex group per label
_LEXICON: dict[str, tuple[str, ...]] = {
    "Geopolitical": (
        r"war", r"invasion", r"sanction", r"tariff", r"embargo", r"missile",
        r"conflict", r"ceasefire", r"peace (agreement|talks|deal)", r"opec",
        r"trade (war|dispute|deal|pact)", r"export (control|ban|restriction)",
        r"chokepoint", r"shipping lane", r"geopolitic",
    ),
    "Macroeconomic": (
        r"inflation", r"cpi", r"gdp", r"recession", r"interest rates?",
        r"rate (hike|cut|pause)", r"central bank", r"federal reserve|the fed",
        r"treasury yields?", r"unemployment", r"payrolls?", r"pmi",
        r"guidance", r"earnings", r"quarterly results?", r"buyback",
        r"dividend", r"margins?", r"demand", r"revenue",
    ),
    "Credit Event": (
        r"downgrade", r"upgrade[sd]?", r"default", r"bankrupt", r"chapter 11",
        r"debt", r"bond", r"credit (rating|spread|rating agency|curve)",
        r"covenant", r"refinanc\w+", r"moody'?s?", r"s&p global ratings",
        r"fitch", r"junk status", r"liquidity crisis",
    ),
    "Merger/Acquisition": (
        r"merger", r"acqui\w+", r"takeover", r"bid", r"buyout", r"deal talks",
        r"antitrust probe", r"competition watchdog", r"regulators? (block|probe)",
    ),
    "Product Launch": (
        r"launch", r"unveil", r"reveals?", r"rolls out", r"roll back",
        r"new (product|platform|chip|model|suite|line|app|service)",
        r"pilots?", r"beta", r"flagship", r"next-generation", r"demo",
    ),
}

_COMPILED: dict[str, tuple[re.Pattern[str], ...]] = {
    label: tuple(re.compile(p, re.IGNORECASE) for p in pats)
    for label, pats in _LEXICON.items()
}


@dataclass
class EventClassification:
    label: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)
    lexicon_votes: dict[str, int] = field(default_factory=dict)


_lock = threading.Lock()
_zs_pipeline = None


def _get_zs_pipeline():
    global _zs_pipeline
    if _zs_pipeline is None:
        with _lock:
            if _zs_pipeline is None:
                from transformers import pipeline as hf_pipeline

                logger.info("Loading event model %s", settings.event_model)
                _zs_pipeline = hf_pipeline(
                    "zero-shot-classification",
                    model=settings.event_model,
                )
    return _zs_pipeline


def load_model() -> None:
    _get_zs_pipeline()


def is_loaded() -> bool:
    return _zs_pipeline is not None


def lexicon_votes(text: str) -> dict[str, int]:
    votes: dict[str, int] = {}
    for label, patterns in _COMPILED.items():
        n = sum(1 for p in patterns if p.search(text))
        if n:
            votes[label] = n
    return votes


def classify(text: str, event_hint: str | None = None,
             use_model: bool = True) -> EventClassification:
    """0.7 x zero-shot NLI + 0.3 x lexicon votes (+0.10 prior for event_hint).

    use_model=False is the lexicon-only fast path used by the backfill.
    """
    votes = lexicon_votes(text)
    total_votes = sum(votes.values()) or 1

    zs_probs: dict[str, float] = {}
    if use_model:
        zs = _get_zs_pipeline()(text, candidate_labels=list(EVENT_LABELS),
                                hypothesis_template=_HYPOTHESIS)
        zs_probs = dict(zip(zs["labels"], zs["scores"]))

    scores: dict[str, float] = {}
    for label in EVENT_LABELS:
        lex = votes.get(label, 0) / total_votes
        scores[label] = 0.7 * zs_probs.get(label, 0.0) + 0.3 * lex
    if event_hint in EVENT_LABELS:
        scores[event_hint] += 0.10

    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1.0
    confidence = scores[best] / total
    if use_model:
        confidence = max(confidence, zs_probs.get(best, 0.0))
    return EventClassification(label=best, confidence=round(min(confidence, 0.99), 4),
                               scores={k: round(v, 4) for k, v in scores.items()},
                               lexicon_votes=votes)
