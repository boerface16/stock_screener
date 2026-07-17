from typing import Dict, Set, Tuple

from config import Config

_TRENDING_URL = "https://api.stocktwits.com/api/2/trending/symbols.json"


def fetch_stocktwits_trending(cfg: Config) -> Tuple[Set[str], Dict[str, int]]:
    """Returns (ticker_set, rank_map) where rank_map[ticker] = 1-based rank.

    Plain requests gets 403 here regardless of User-Agent — StockTwits fronts this endpoint
    with a bot check. cloudscraper solves the challenge and returns 200 (verified: 30 symbols).
    """
    tickers: Set[str] = set()
    rank_map: Dict[str, int] = {}
    try:
        import cloudscraper
        resp = cloudscraper.create_scraper().get(_TRENDING_URL, timeout=cfg.request_timeout * 2)
        resp.raise_for_status()
        data = resp.json()
        symbols = data.get("symbols", [])
        for i, item in enumerate(symbols, start=1):
            sym = item.get("symbol", "").upper()
            if sym and sym.isalpha() and 1 <= len(sym) <= 5:
                tickers.add(sym)
                rank_map[sym] = i
    except Exception as e:
        print(f"[WARN] StockTwits trending unavailable: {e}")
    return tickers, rank_map
