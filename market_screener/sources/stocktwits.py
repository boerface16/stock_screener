import time
from typing import Dict, List, Set, Tuple

from config import Config

_TRENDING_URL = "https://api.stocktwits.com/api/2/trending/symbols.json"
_STREAM_URL = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"


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


def fetch_stocktwits_sentiment(cfg: Config, tickers: List[str]) -> Dict[str, Dict[str, int]]:
    """Per-ticker Bull/Bear counts from StockTwits message streams.

    Each message may carry a poster-set label at `entities.sentiment.basic` ("Bullish"/"Bearish");
    ~30-50% do (measured: AAPL 9/30, MU 15/30). Counting those labels *is* the social signal — no
    lexicon, and it covers the pool rather than whatever is trending, which is why Reddit titles
    (populated for ~1.5% of the pool) were retired from the sentiment path.

    Budgeted and throttled: the unauthenticated API allows ~200 requests/hour, so only the first
    `budget` tickers are fetched — `tickers` arrives in confirmation-rank order, so the budget
    spends on the most-corroborated names. A 429 backs off once and stops; the tail simply has no
    social_sentiment and renormalizes away (never imputed). Coverage is recorded by the caller.
    """
    import cloudscraper
    scraper = cloudscraper.create_scraper()
    out: Dict[str, Dict[str, int]] = {}
    budget = min(len(tickers), cfg.stocktwits_stream_budget)
    for i, ticker in enumerate(tickers[:budget]):
        try:
            resp = scraper.get(_STREAM_URL.format(ticker), timeout=cfg.request_timeout * 2)
            if resp.status_code == 429:
                print(f"[WARN] StockTwits streams rate-limited at {i}/{budget} — "
                      f"stopping (coverage {len(out)})")
                break
            resp.raise_for_status()
            bull = bear = 0
            for msg in resp.json().get("messages", []):
                sentiment = (msg.get("entities") or {}).get("sentiment") or {}
                label = sentiment.get("basic") if isinstance(sentiment, dict) else None
                if label == "Bullish":
                    bull += 1
                elif label == "Bearish":
                    bear += 1
            if bull + bear >= cfg.stocktwits_min_messages:
                out[ticker] = {"bull": bull, "bear": bear}
        except Exception as e:
            print(f"[WARN] StockTwits stream failed for {ticker}: {e}")
        time.sleep(cfg.stocktwits_stream_delay)
    print(f"[INFO] StockTwits sentiment: {len(out)}/{budget} tickers labeled")
    return out
