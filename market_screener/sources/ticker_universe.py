import json
import requests
import pandas as pd
from typing import Set

_RAW_BASE = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main"
_MARKET_FILES = [
    f"{_RAW_BASE}/nyse/nyse_full_tickers.json",
    f"{_RAW_BASE}/nasdaq/nasdaq_full_tickers.json",
    f"{_RAW_BASE}/amex/amex_full_tickers.json",
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def load_valid_tickers(timeout: int = 10) -> Set[str]:
    tickers: Set[str] = set()
    fetched_any = False

    for url in _MARKET_FILES:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = json.loads(resp.text)
            for item in data:
                sym = item.get("symbol", "").strip().upper()
                if sym and 1 <= len(sym) <= 5:
                    tickers.add(sym)
            fetched_any = True
        except Exception as e:
            print(f"[WARN] Could not fetch ticker list from {url}: {e}")

    if not fetched_any or len(tickers) < 100:
        print("[INFO] Falling back to Wikipedia S&P500 + NASDAQ100 for ticker whitelist")
        tickers.update(_fetch_wikipedia_tickers())

    print(f"[INFO] Ticker whitelist loaded: {len(tickers)} symbols")
    return tickers


def _fetch_wikipedia_tickers() -> Set[str]:
    tickers: Set[str] = set()
    urls = [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "https://en.wikipedia.org/wiki/Nasdaq-100",
    ]
    for url in urls:
        try:
            tables = pd.read_html(url, storage_options={"User-Agent": "Mozilla/5.0"})
            for table in tables:
                for col in ["Symbol", "Ticker", "Ticker symbol"]:
                    if col in table.columns:
                        syms = table[col].dropna().astype(str).str.upper()
                        tickers.update(s for s in syms if s.isalpha() and 1 <= len(s) <= 5)
                        break
        except Exception as e:
            print(f"[WARN] Wikipedia whitelist fetch failed: {e}")
    return tickers
