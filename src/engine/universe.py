from dataclasses import dataclass, field


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    sector: str
    aliases: tuple[str, ...] = field(default=())


UNIVERSE: tuple[Company, ...] = (
    Company("AAPL", "Apple Inc.", "Technology", ("Apple", "iPhone")),
    Company("MSFT", "Microsoft Corp.", "Technology", ("Microsoft",)),
    Company("NVDA", "NVIDIA Corp.", "Technology", ("NVIDIA", "Nvidia")),
    Company("GOOGL", "Alphabet Inc.", "Technology", ("Alphabet", "Google")),
    Company("AMZN", "Amazon.com Inc.", "Consumer", ("Amazon",)),
    Company("META", "Meta Platforms Inc.", "Technology", ("Meta", "Facebook")),
    Company("JPM", "JPMorgan Chase & Co.", "Financials", ("JPMorgan", "JP Morgan")),
    Company("BAC", "Bank of America Corp.", "Financials", ("Bank of America",)),
    Company("GS", "The Goldman Sachs Group Inc.", "Financials", ("Goldman Sachs",)),
    Company("XOM", "Exxon Mobil Corp.", "Energy", ("Exxon", "ExxonMobil")),
    Company("CVX", "Chevron Corp.", "Energy", ("Chevron",)),
    Company("WMT", "Walmart Inc.", "Consumer", ("Walmart",)),
    Company("KO", "The Coca-Cola Company", "Consumer", ("Coca-Cola", "Coke")),
    Company("BA", "The Boeing Company", "Industrials", ("Boeing",)),
)

SECTORS: tuple[str, ...] = tuple(sorted({c.sector for c in UNIVERSE}))

SECTOR_MEMBERS: dict[str, list[str]] = {}
for _c in UNIVERSE:
    SECTOR_MEMBERS.setdefault(_c.sector, []).append(_c.ticker)

TICKERS: tuple[str, ...] = tuple(c.ticker for c in UNIVERSE)

# text mentioning these (and no company) becomes a market-scoped signal
MARKET_ALIASES: tuple[str, ...] = (
    "the market", "stock market", "equities", "wall street", "S&P",
    "S&P 500", "federal reserve", "the fed", "central bank", "ecb",
    "inflation", "recession", "gdp", "interest rates", "rate hike",
    "rate cut", "cpi", "unemployment", "treasury yields", "opec",
)

BY_TICKER: dict[str, Company] = {c.ticker: c for c in UNIVERSE}


def sector_of(ticker: str) -> str:
    return BY_TICKER[ticker].sector
