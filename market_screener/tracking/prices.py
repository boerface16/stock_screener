"""Daily adjusted closes from yfinance, cached to disk.

The tracking tab is online-only by nature — you cannot know a stock's price *after* a screen from
a frozen snapshot. So this is the one place the app touches the network at view time; the screener
itself stays deterministic and offline. Closes are **adjusted** (auto_adjust=True) so dividends and
splits are total-return, not phantom drops. Each ticker is cached as a CSV under
`tracking_cache_dir`; a stale cache is refetched in full (daily bars are a few hundred rows, and a
new dividend/split silently rewrites history, so a partial append would drift).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, Optional

import pandas as pd

from config import Config

# Consider a cache fresh if its last bar is within this many days of today. Wide enough to skip
# refetching over a weekend/holiday, narrow enough to pick up a genuinely new trading day.
_FRESH_DAYS = 4


def _cache_path(cfg: Config, ticker: str) -> str:
    return os.path.join(cfg.tracking_cache_dir, f"{ticker.upper()}.csv")


def _read_cache(path: str) -> Optional[pd.Series]:
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, parse_dates=["Date"])
    except (OSError, ValueError, KeyError):
        return None
    if df.empty or "Close" not in df:
        return None
    s = pd.Series(df["Close"].to_numpy(), index=pd.DatetimeIndex(df["Date"]), name=ticker_of(path))
    return s.dropna()


def ticker_of(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _is_fresh(series: pd.Series) -> bool:
    if series is None or series.empty:
        return False
    return (date.today() - series.index.max().date()).days <= _FRESH_DAYS


def _fetch(ticker: str, start: Optional[date]) -> Optional[pd.Series]:
    """yfinance adjusted closes, indexed by date. None on any failure or empty result."""
    import yfinance as yf
    try:
        df = yf.download(
            ticker,
            start=start.isoformat() if start else None,
            period=None if start else "5y",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df:
        return None
    close = df["Close"]
    if isinstance(close, pd.DataFrame):        # MultiIndex columns when yfinance wraps one ticker
        close = close.iloc[:, 0]
    s = pd.Series(close.to_numpy(dtype=float), index=pd.DatetimeIndex(df.index), name=ticker)
    return s.dropna()


def get_closes(cfg: Config, ticker: str, start: Optional[date] = None,
               refresh: bool = True) -> Optional[pd.Series]:
    """Adjusted daily closes for `ticker`, cache-first. Refetches when the cache is stale (unless
    `refresh=False`, e.g. offline). `start` bounds the fetch when there is no cache yet."""
    path = _cache_path(cfg, ticker)
    cached = _read_cache(path)
    if cached is not None and (not refresh or _is_fresh(cached)):
        return cached
    if not refresh:
        return cached

    fetched = _fetch(ticker, start)
    if fetched is None or fetched.empty:
        return cached                          # keep whatever we had rather than losing it
    os.makedirs(cfg.tracking_cache_dir, exist_ok=True)
    fetched.rename_axis("Date").rename("Close").to_frame().to_csv(path)
    return fetched


def get_many(cfg: Config, tickers: Iterable[str], start: Optional[date] = None,
             refresh: bool = True) -> Dict[str, pd.Series]:
    """Closes for many tickers, keyed by symbol. Missing/failed tickers are omitted."""
    out: Dict[str, pd.Series] = {}
    for t in sorted(set(tickers)):
        s = get_closes(cfg, t, start=start, refresh=refresh)
        if s is not None and not s.empty:
            out[t] = s
    return out


def benchmark_closes(cfg: Config, start: Optional[date] = None,
                     refresh: bool = True) -> Optional[pd.Series]:
    return get_closes(cfg, cfg.benchmark, start=start, refresh=refresh)
