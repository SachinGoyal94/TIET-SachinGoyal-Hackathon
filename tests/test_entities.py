from src.engine.nlp.entities import match_entities


def test_company_name_matching():
    matches = match_entities("Apple unveiled a new chip and Microsoft followed")
    tickers = [m.ticker for m in matches]
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_cashtag_matching():
    matches = match_entities("$AAPL ripping 2% while $XOM slips")
    tickers = [m.ticker for m in matches]
    assert "AAPL" in tickers
    assert "XOM" in tickers


def test_unknown_cashtag_ignored():
    assert match_entities("$XYZ to the moon") == []


def test_market_keywords():
    matches = match_entities("The Federal Reserve hikes interest rates again")
    assert any(m.ticker is None and m.sector is None for m in matches)


def test_sector_keyword_matching():
    matches = match_entities("Energy names rally across the sector")
    sectors = [m.sector for m in matches if m.sector]
    assert "Energy" in sectors


def test_plain_text_no_match():
    assert match_entities("The quick brown fox jumps over the lazy dog") == []
