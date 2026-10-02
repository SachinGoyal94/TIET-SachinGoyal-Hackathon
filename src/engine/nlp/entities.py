import re
from dataclasses import dataclass

from src.engine.universe import BY_TICKER, MARKET_ALIASES, SECTORS, UNIVERSE


@dataclass(frozen=True)
class EntityMatch:
    ticker: str | None
    sector: str | None
    name: str


def _word_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase)
    if phrase[-1].isalnum():
        escaped += r"s?\b"
    return re.compile(r"\b" + escaped, re.IGNORECASE)


_MATCHERS: list[tuple[re.Pattern[str], str | None, str | None]] = [
    (_word_pattern(alias), c.ticker, c.sector)
    for c in UNIVERSE
    for alias in (c.name.replace(" Inc.", "").replace(" Corp.", "")
                  .replace(" & Co.", "").replace(" The ", " ").strip(),) + c.aliases
    if len(alias) > 2
]
for _sector in SECTORS:
    _MATCHERS.append((_word_pattern(_sector), None, _sector))

_MARKET_MATCHERS = [_word_pattern(a) for a in MARKET_ALIASES]
_CASHTAG = re.compile(r"\$([A-Z]{1,6})\b")


def match_entities(text: str) -> list[EntityMatch]:
    matches: list[EntityMatch] = []
    seen: set[str] = set()

    def add(ticker: str | None, sector: str | None) -> None:
        key = ticker or f"sector:{sector}"
        if key not in seen:
            seen.add(key)
            matches.append(EntityMatch(ticker=ticker, sector=sector,
                                       name=ticker or (sector or "")))

    for ticker in _CASHTAG.findall(text):
        if ticker in BY_TICKER:
            add(ticker, BY_TICKER[ticker].sector)

    for pattern, ticker, sector in _MATCHERS:
        if pattern.search(text):
            add(ticker, sector)

    if not matches and any(p.search(text) for p in _MARKET_MATCHERS):
        add(None, None)
    return matches
