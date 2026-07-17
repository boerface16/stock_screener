import pandas as pd
from typing import Set
from config import Config


_SCREENER_URLS = [
    "https://finance.yahoo.com/screener/predefined/most_actives",
    "https://finance.yahoo.com/screener/predefined/day_gainers",
    "https://finance.yahoo.com/screener/predefined/day_losers",
    "https://finance.yahoo.com/screener/predefined/growth_technology_stocks",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_yahoo_movers(cfg: Config) -> Set[str]:
    tickers: Set[str] = set()
    try:
        import yfinance as yf
        for screen in ["most_actives", "day_gainers", "day_losers"]:
            try:
                data = yf.screen(screen, size=100)
                if data and "quotes" in data:
                    for q in data["quotes"]:
                        sym = q.get("symbol", "")
                        if sym and "." not in sym:
                            tickers.add(sym.upper())
            except Exception as e:
                print(f"[WARN] Yahoo screener '{screen}' failed: {e}")
    except Exception as e:
        print(f"[WARN] Yahoo Finance movers unavailable: {e}")
    return tickers


def fetch_wikipedia_index() -> Set[str]:
    """Last-resort pool fallback when every primary source fails.

    The User-Agent is load-bearing: without it Wikipedia returns 403 and this returned 0
    tickers — an emergency parachute packed inside-out, silently. Its near-twin
    `ticker_universe.py:load_valid_tickers` passed one all along and returned 501.
    """
    tickers: Set[str] = set()
    urls = [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "https://en.wikipedia.org/wiki/Nasdaq-100",
    ]
    for url in urls:
        try:
            tables = pd.read_html(url, storage_options=_HEADERS)
            for table in tables:
                for col in ["Symbol", "Ticker", "Ticker symbol"]:
                    if col in table.columns:
                        syms = table[col].dropna().astype(str).str.upper()
                        tickers.update(s for s in syms if s.isalpha() and 1 <= len(s) <= 5)
                        break
        except Exception as e:
            print(f"[WARN] Wikipedia fallback failed for {url}: {e}")
    return tickers
