"""Synthetic news & tweet generator.

Why synthetic data? The submission guidelines require either public or
self-generated data with no licensing risk, and a deterministic generator
gives us: (a) unlimited demo volume, (b) controllable high-impact events so
the stress-testing module always has something to trigger on, and (c) an
offline-safe fallback when live feeds (GDELT) are unreachable.

Templates are grouped by event type and polarity and combined with the
index universe plus macro/geopolitical actors to produce realistic-looking
financial headlines and social posts.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.engine.universe import BY_TICKER, TICKERS, Company

# Macro actors that generate market-scoped events.
ACTORS = ("the Federal Reserve", "OPEC", "the ECB", "G7 finance ministers", "regulators")

WEIGHTED_LABELS = (
    # (label, weight) — tuned so geopolitical/credit events are rarer but
    # do occur, which is exactly what Module B's trigger needs.
    ("Macroeconomic", 34),
    ("Product Launch", 22),
    ("Geopolitical", 16),
    ("Credit Event", 14),
    ("Merger/Acquisition", 10),
    ("Other", 4),
)
_LABELS, _WEIGHTS = zip(*WEIGHTED_LABELS)


@dataclass(frozen=True)
class GeneratedItem:
    text: str
    event_label: str
    source: str  # synthetic_news | synthetic_tweet
    published_at: datetime


def _co(rng: random.Random) -> Company:
    return BY_TICKER[rng.choice(TICKERS)]


# --- Headline templates: (event_label, polarity, template) --------------------
# {co} -> company name, {tick} -> ticker, {pct} -> small percentage,
# {bps} -> basis points, {bn} -> billions, {actor} -> macro actor.
_T: list[tuple[str, int, str]] = [
    # --- Product Launch ---
    ("Product Launch", 1, "{co} unveils next-generation platform to strong early reviews from analysts"),
    ("Product Launch", 1, "{co} launches AI-powered suite, first customers report double-digit efficiency gains"),
    ("Product Launch", 1, "{co} reveals new flagship product line ahead of schedule"),
    ("Product Launch", 1, "{co} pilot program expands after successful early rollout"),
    ("Product Launch", -1, "{co} product event underwhelms investors as shares slip {pct}%"),
    ("Product Launch", -1, "{co} flagship launch delayed by supply constraints"),
    ("Product Launch", -1, "{co} pulls software update after users report widespread issues"),
    ("Product Launch", 0, "{co} to host annual developer conference next month"),
    # --- Merger / Acquisition ---
    ("Merger/Acquisition", 1, "{co} in talks to acquire regional rival in ${bn} billion deal"),
    ("Merger/Acquisition", 1, "{co} agrees to buy niche competitor, analysts see immediate accretion"),
    ("Merger/Acquisition", 1, "Board of {co} approves strategic acquisition to expand margins"),
    ("Merger/Acquisition", -1, "{co} acquisition talks collapse over price disagreement"),
    ("Merger/Acquisition", -1, "Regulators open in-depth probe into {co} takeover bid"),
    ("Merger/Acquisition", 0, "Speculation swirls around potential bid for {co}"),
    # --- Macroeconomic (company-scoped) ---
    ("Macroeconomic", 1, "{co} raises full-year guidance as margins expand {bps} bps"),
    ("Macroeconomic", 1, "{co} beats earnings estimates on resilient consumer demand"),
    ("Macroeconomic", 1, "{co} announces ${bn} billion buyback after record quarter"),
    ("Macroeconomic", -1, "{co} cuts outlook citing softer demand and rising input costs"),
    ("Macroeconomic", -1, "{co} margins compress as wage pressures build {pct}%"),
    ("Macroeconomic", -1, "{co} warns of demand headwinds into next quarter, stock drops {pct}%"),
    ("Macroeconomic", 0, "{co} results in line with street expectations"),
    # --- Macroeconomic (market-scoped) ---
    ("Macroeconomic", 1, "{actor} signals steady policy path, treasury yields ease"),
    ("Macroeconomic", 1, "Inflation cools to {pct}% lifting rate-cut hopes across equities"),
    ("Macroeconomic", -1, "{actor} hikes rates {bps} bps and flags further tightening"),
    ("Macroeconomic", -1, "Hot inflation print at {pct}% stokes fears of prolonged high rates"),
    ("Macroeconomic", -1, "Flash PMI contracts for a third month, recession chatter grows on desks"),
    ("Macroeconomic", 0, "Markets drift sideways ahead of {actor} decision this week"),
    # --- Geopolitical ---
    ("Geopolitical", -1, "Conflict escalation near key shipping chokepoint sends crude up {pct}%"),
    ("Geopolitical", -1, "New sanctions package disrupts supply chains, energy names tumble {pct}%"),
    ("Geopolitical", -1, "Tit-for-tat tariff escalation hits semiconductor supply chains"),
    ("Geopolitical", -1, "Missile test prompts air-pace closures over critical trade corridor"),
    ("Geopolitical", -1, "Export controls tightened on advanced chips, {co} supply base in crossfire"),
    ("Geopolitical", 1, "Ceasefire agreement lifts risk appetite, crude gives back {pct}%"),
    ("Geopolitical", 1, "Trade deal removes tariffs on key industrial goods"),
    ("Geopolitical", 1, "{actor} de-escalation talks make unexpected progress"),
    ("Geopolitical", 0, "Summit of {actor} opens with agenda dominated by trade policy"),
    # --- Credit Event ---
    ("Credit Event", -1, "Rating agencies downgrade {co} citing rising leverage, spreads gap wider"),
    ("Credit Event", -1, "{co} creditor cohort braces for covenant stress as defaults climb {pct}%"),
    ("Credit Event", -1, "Regional lender defaults on unsecured notes, contagion fear spreads"),
    ("Credit Event", -1, "{co} pulls bond sale as investors demand {bps} bps more in yield"),
    ("Credit Event", 1, "{co} upgrades spark rally in investment-grade credit"),
    ("Credit Event", 1, "{co} refinances maturing debt at {bps} bps tighter spreads"),
    ("Credit Event", 1, "{co} balance sheet strength earns outlook revision to positive"),
    ("Credit Event", 0, "Credit traders report two-way flows in {co} curve"),
    # --- Other ---
    ("Other", 0, "{co} to webcast investor day later this month"),
    ("Other", 0, "{co} files routine annual compliance disclosure"),
    ("Other", 1, "{co} wins industry award for sustainability reporting"),
    ("Other", -1, "{co} faces shareholder proposal on governance practices"),
]

# --- Tweet templates (shorter, more colloquial, hashtags) ---------------------
_TW: list[tuple[str, int, str]] = [
    ("Macroeconomic", 1, "$TICK ripping {pct}% — guidance raise is no joke, best execution on the street"),
    ("Macroeconomic", -1, "$TICK down {pct}% on the guidance cut, margins getting crushed. staying out"),
    ("Macroeconomic", 0, "$TICK flat into print. nobody wants to take risk before the number"),
    ("Product Launch", 1, "saw the new $TICK demo in person — this changes the category, seriously"),
    ("Product Launch", -1, "$TICK launch event was a snooze, sell the news much?"),
    ("Merger/Acquisition", 1, "$TICK acquiring their competitor at that price is actually cheap. bull case intact"),
    ("Merger/Acquisition", -1, "that $TICK deal falling apart is ugly. management credibility gone"),
    ("Credit Event", -1, "credit desk chatter: $TICK spreads blowing out, {bps} bps wider. not nothing"),
    ("Credit Event", 1, "$TICK refinanced cheaper than expected. balance sheet fear was overdone"),
    ("Geopolitical", -1, "oil spiking {pct}% on the strait news, risk-off everywhere. $TICK energy exposure matters now"),
    ("Geopolitical", 1, "ceasefire headline = risk-on. crude dumps {pct}%, equities breathe"),
    ("Geopolitical", 0, "all eyes on the summit. nothing priced in either way yet"),
    ("Other", 0, "quiet tape today. $TICK rangebound, waiting for the macro"),
]


def _fill(template: str, rng: random.Random, co: Company | None) -> str:
    out = template
    if "{co}" in out:
        assert co is not None
        out = out.replace("{co}", co.name.rstrip("."))
    if "$TICK" in out:
        assert co is not None
        out = out.replace("$TICK", co.ticker)
    out = out.replace("{tick}", co.ticker if co else "")
    out = out.replace("{pct}", f"{rng.uniform(0.6, 4.5):.1f}")
    out = out.replace("{bps}", f"{rng.randint(25, 300)}")
    out = out.replace("{bn}", f"{rng.uniform(0.8, 14):.1f}")
    out = out.replace("{actor}", rng.choice(ACTORS))
    return out


def generate_item(rng: random.Random, *, allow_market_scope: bool = True) -> GeneratedItem:
    """One synthetic item: a news headline or a social post."""
    label = rng.choices(_LABELS, weights=_WEIGHTS, k=1)[0]
    is_tweet = rng.random() < 0.4

    if is_tweet:
        pool = [t for t in _TW if t[0] == label and (allow_market_scope or "$TICK" in t[1])]
        if not pool:
            pool = [t for t in _TW if t[0] == label]
        _, polarity, template = rng.choice(pool)
        co = _co(rng)
        text = _fill(template, rng, co)
        return GeneratedItem(text=text, event_label=label, source="synthetic_tweet",
                             published_at=utcnow_floor())
    # News: market-scoped templates (no {co} token) are for macro/geo events;
    # company templates pick a name from the universe.
    pool = [t for t in _T if t[0] == label]
    candidates = pool if allow_market_scope else [t for t in pool if "{co}" in t[2] or "$TICK" in t[2]]
    _, polarity, template = rng.choice(candidates or pool)
    if "{co}" in template:
        co = _co(rng)
    elif "$TICK" in template:
        co = _co(rng)
    else:
        co = None
    text = _fill(template, rng, co)
    return GeneratedItem(text=text, event_label=label, source="synthetic_news",
                         published_at=utcnow_floor())


def utcnow_floor() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def generate_history(rng: random.Random, days: int, per_day: int) -> list[GeneratedItem]:
    """A realistic-looking backlog: business-hour weighted timestamps."""
    items: list[GeneratedItem] = []
    now = utcnow_floor()
    for d in range(days, 0, -1):
        base_day = now - timedelta(days=d)
        for _ in range(per_day):
            item = generate_item(rng)
            hour = min(22, max(6, int(rng.gauss(14, 4))))
            ts = base_day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
            items.append(GeneratedItem(item.text, item.event_label, item.source, ts))
    items.sort(key=lambda i: i.published_at)
    return items
