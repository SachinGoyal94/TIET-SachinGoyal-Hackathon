from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from src.engine.nlp import entities, events, impact, sentiment


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


def analyze_text(text: str, event_hint: str | None = None,
                 use_model: bool = True) -> RiskSignal:
    """Full pipeline over one item (live path, with the zero-shot model)."""
    return analyze_batch([{"text": text, "event_hint": event_hint,
                           "use_model": use_model}])[0]


def analyze_batch(items: list[dict]) -> list[RiskSignal]:
    """Batched analysis (backfill path). Each item: {text, event_hint?, use_model?}."""
    items = [dict(i, text=(i.get("text") or "").strip()) for i in items]
    sentiments = sentiment.score_batch([i["text"] for i in items])
    signals: list[RiskSignal] = []
    for item, s in zip(items, sentiments):
        text = item["text"]
        cls = events.classify(
            text,
            event_hint=item.get("event_hint"),
            use_model=bool(item.get("use_model", False)),
        )
        imp = impact.score_impact(cls.label, s, n_sources=1)
        signals.append(RiskSignal(
            text=text,
            text_hash=hashlib.sha1(text.encode("utf-8")).hexdigest(),
            sentiment_score=s,
            event_label=cls.label,
            event_confidence=cls.confidence,
            impact_score=imp.score,
            impact_breakdown=imp,
            entities=entities.match_entities(text),
            model_versions={
                "sentiment": "finbert-v0",
                "events": "nli-lexicon-v0" if item.get("use_model") else "lexicon-v0",
                "impact": "composite-v0",
            },
        ))
    return signals
