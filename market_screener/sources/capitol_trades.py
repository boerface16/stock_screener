import re
import time
from datetime import datetime
from typing import Dict, Set

from config import Config
from sources.crawler import scrape_urls

_TRADES_URL = "https://www.capitoltrades.com/trades?pageSize=96&page={page}"
_ARTICLES_URL = "https://www.capitoltrades.com/articles"

_DATE_RE = re.compile(r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b')
_BUY_RE = re.compile(r'\b(buy|purchase|bought)\b', re.IGNORECASE)
_SELL_RE = re.compile(r'\b(sell|sale|sold)\b', re.IGNORECASE)
# Matches "AMGN:US" or plain "AMGN" in a table cell
_TICKER_CELL_RE = re.compile(r'^([A-Z]{1,5})(?::US)?$')


def _parse_markdowns(markdowns: list, valid_tickers: Set[str], lookback_days: int = 60) -> Dict[str, Dict]:
    cutoff = time.time() - (lookback_days * 86400)
    recent_cutoff = time.time() - (14 * 86400)
    trades: Dict[str, Dict] = {}

    for md in markdowns:
        for line in md.splitlines():
            if '|' not in line:
                continue

            # Date — Capitol Trades format: "22 Apr 2026"
            date_match = _DATE_RE.search(line)
            if date_match:
                try:
                    trade_ts = datetime.strptime(date_match.group(1), "%d %b %Y").timestamp()
                except Exception:
                    continue
                if trade_ts < cutoff:
                    continue
            else:
                continue

            # Ticker — handles "AMGN:US" and plain "AMGN" formats
            cells = [c.strip() for c in line.split('|') if c.strip()]
            ticker = None
            for cell in cells:
                m = _TICKER_CELL_RE.match(cell)
                if m:
                    candidate = m.group(1)
                    if not valid_tickers or candidate in valid_tickers:
                        ticker = candidate
                        break
            if not ticker:
                continue

            # Trade type
            is_buy = bool(_BUY_RE.search(line))
            is_sell = bool(_SELL_RE.search(line))
            if not is_buy and not is_sell:
                continue

            recency = 1.5 if trade_ts >= recent_cutoff else 1.0

            if ticker not in trades:
                trades[ticker] = {"buy_weight": 0.0, "sell_weight": 0.0}

            if is_buy:
                trades[ticker]["buy_weight"] += recency
            elif is_sell:
                trades[ticker]["sell_weight"] += recency

    return trades


def fetch_capitol_trades(cfg: Config, valid_tickers: Set[str]) -> Dict[str, Dict]:
    """Scrape Capitol Trades and return {ticker: {buy_weight, sell_weight}}."""
    urls = [_TRADES_URL.format(page=p) for p in range(1, cfg.capitol_trades_pages + 1)]
    urls.append(_ARTICLES_URL)

    pages = scrape_urls(urls, timeout_ms=cfg.request_timeout * 3 * 1000)
    markdowns = [p["markdown"] for p in pages if p["markdown"]]

    trades = _parse_markdowns(markdowns, valid_tickers, lookback_days=60)
    print(f"[INFO]   Capitol Trades: {len(trades)} tickers with recent congress activity")
    return trades
