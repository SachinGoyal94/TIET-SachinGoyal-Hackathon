from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from src.engine.config import settings
from src.engine.nlp import entities, entity_sentiment, events, impact, sentiment

logger = logging.getLogger(__name__)


@dataclass
class RiskSignal:
    text: str
    text_hash: str
    sentiment_score: float
    event_label: str
    event_confidence: float
    impact_score: float
    impact_breakdown: impact.ImpactBreakdown
    entities: list[entities.EntityMatch] = field(default_factory=list)
    model_versions: dict[str, str] = field(default_factory=dict)
    # ticker -> sentiment from the per-entity extraction layer; empty when the
    # extractor is off or the headline mentions no universe company
    per_entity: dict[str, float] = field(default_factory=dict)

    @property
    def primary_ticker(self) -> str | None:
        company = [e for e in self.entities if e.ticker]
        return company[0].ticker if company else None

    def scope_entity_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for e in self.entities:
            if e.ticker:
                pairs.append(("company", e.ticker))
                seen.add(e.ticker)
                if e.sector and e.sector not in seen:
                    pairs.append(("sector", e.sector))
                    seen.add(e.sector)
        if not pairs:
            pairs.append(("market", "MARKET"))
        return pairs

    def sentiment_for(self, scope: str, entity: str) -> float:
        if scope == "company" and entity in self.per_entity:
            return self.per_entity[entity]
        return self.sentiment_score


def analyze_text(text: str, event_hint: str | None = None,
                 use_model: bool = True) -> RiskSignal:
    """Full pipeline over one item (live path, with the zero-shot model)."""
    return analyze_batch([{"text": text, "event_hint": event_hint,
                           "use_model": use_model}])[0]


def analyze_batch(items: list[dict]) -> list[RiskSignal]:
    """Batched analysis (backfill path). Each item: {text, event_hint?, use_model?,
    extract_entities?}."""
    items = [dict(i, text=(i.get("text") or "").strip()) for i in items]
    sentiments = sentiment.score_batch([i["text"] for i in items])
    sent_version = "finbert-ft-v1" if "finbert-ft" in settings.active_sentiment_model else "finbert-v0"

    extractor_on = entity_sentiment.is_configured()

    signals: list[RiskSignal] = []
    for item, s in zip(items, sentiments):
        text = item["text"]
        cls = events.classify(
            text,
            event_hint=item.get("event_hint"),
            use_model=bool(item.get("use_model", False)),
        )
        imp = impact.score_impact(cls.label, s, n_sources=1)
        matches = entities.match_entities(text)
        signal = RiskSignal(
            text=text,
            text_hash=hashlib.sha1(text.encode("utf-8")).hexdigest(),
            sentiment_score=s,
            event_label=cls.label,
            event_confidence=cls.confidence,
            impact_score=imp.score,
            impact_breakdown=imp,
            entities=matches,
            model_versions={
                "sentiment": sent_version,
                "events": "nli-lexicon-v0" if item.get("use_model") else "lexicon-v0",
                "impact": "composite-v0",
            },
        )

        # extraction is opt-out: the live path gets it, the backfill disables it
        if extractor_on and item.get("extract_entities", True) \
                and any(m.ticker for m in matches):
            try:
                candidates = [m.name for m in matches if m.ticker]
                per_entity = entity_sentiment.extract(
                    text, magnitude=abs(s), candidates=candidates)
                by_name = {e.name.lower(): e.sentiment for e in per_entity}
                signal.per_entity = {
                    m.ticker: by_name[m.name.lower()]
                    for m in matches
                    if m.ticker and m.name.lower() in by_name
                }
                if signal.per_entity:
                    signal.model_versions["sentiment"] += "+llm-entity"
            except Exception:
                logger.warning("entity extraction failed, using shared score",
                               exc_info=True)

        signals.append(signal)
    return signals
