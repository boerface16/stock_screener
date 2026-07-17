"""
Ingest — the only module that touches the network on a scoring run.

Everything fetched here lands in the snapshot; `scoring.scorer` then reads nothing else.
That split is what makes `--replay` exact and what makes tuning possible at all: you cannot
A/B two lexicons if re-scoring re-fetches a changed internet (tasks/lessons.md).
"""
import concurrent.futures
import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from config import Config
from market_utils import is_market_open
from scoring.filters import passes_liquidity
from scoring.fundamentals import FINVIZ_PE_KEY, fetch_finviz_pe
from scoring.news import fetch_news
from snapshot import Snapshot
from sources import seed_universe
from sources.stocktwits import fetch_stocktwits_sentiment
from sources.yahoo import fetch_wikipedia_index

# Only Close and Volume are stored. No scorer reads Open/High/Low, and dropping them keeps a
# max-history snapshot to a sane size. Adding an OHLC-based signal later means a re-ingest.
_KEEP_COLS = ["Close", "Volume"]


def _extract_batch(df: pd.DataFrame, tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """Split a yf.download frame into per-ticker Close/Volume frames."""
    out: Dict[str, pd.DataFrame] = {}
    single = not isinstance(df.columns, pd.MultiIndex)
    for t in tickers:
        try:
            sub = pd.DataFrame({c: (df[c] if single else df[c][t]) for c in _KEEP_COLS})
        except (KeyError, IndexError):
            continue
        sub = sub.dropna(subset=["Close"])
        if not sub.empty:
            out[t] = sub
    return out


def _download_prices(tickers: List[str], cfg: Config, label: str, chunk: int = 100) -> Dict[str, pd.DataFrame]:
    """Batched price history. yf.download is ~100x faster than per-ticker .history() and the
    ladder needs `max` history for every name, so per-ticker fetching is no longer viable."""
    out: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i + chunk]
        try:
            df = yf.download(batch, period=cfg.price_history_period, progress=False,
                             auto_adjust=True, threads=True)
            if df is not None and not df.empty:
                out.update(_extract_batch(df, batch))
        except Exception as e:
            print(f"[WARN] {label} price batch {i}-{i+len(batch)} failed: {e}")
        print(f"[INFO] {label}: {min(i + chunk, len(tickers))}/{len(tickers)}")
    return out


def _fetch_info(ticker: str, cfg: Config) -> Optional[dict]:
    """yfinance info with retry, finviz fallback. Prices come from the batch download."""
    for attempt in range(cfg.yfinance_retries):
        try:
            info = yf.Ticker(ticker).info or {}
            if info:
                return info
        except Exception as e:
            if attempt < cfg.yfinance_retries - 1:
                time.sleep(cfg.yfinance_retry_wait)
            else:
                print(f"[WARN] yfinance info failed for {ticker}: {e}")

    try:
        from finviz.screener import Screener
        for stock in Screener(tickers=[ticker], table="Overview"):
            price_str = stock.get("Price", "0")
            vol_str = stock.get("Volume", "0").replace(",", "")
            return {
                "currentPrice": float(price_str) if price_str else 0.0,
                "averageVolume": int(vol_str) if vol_str.isdigit() else 0,
            }
    except Exception:
        pass

    return None


def _reference_universe(cfg: Config) -> List[str]:
    """A deterministic slice of the S&P 500 — the cross-section the grade cuts are drawn from.

    Sorted then truncated, so the same index membership always yields the same reference set.
    """
    sp500 = sorted(fetch_wikipedia_index())
    if not sp500:
        print("[WARN] Reference universe empty — grade cuts will be unavailable this run")
    return sp500[:cfg.reference_universe_size]


def _map(fn, items, workers: int, label: str) -> Dict[str, object]:
    """Threaded fetch keyed by ticker. Results are collected into a dict, so completion
    order cannot leak into the output the way it did through scorer.py's result list."""
    out: Dict[str, object] = {}
    total = len(items)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fn, t): t for t in items}
        for fut in concurrent.futures.as_completed(futures):
            t = futures[fut]
            done += 1
            if done % 50 == 0 or done == total:
                print(f"[INFO] {label}: {done}/{total}")
            try:
                out[t] = fut.result()
            except Exception as e:
                print(f"[WARN] {label} failed for {t}: {e}")
    return out


def ingest(cfg: Config, run_ts: str) -> Snapshot:
    seed = seed_universe(cfg)
    if not seed.pool:
        return Snapshot(run_ts=run_ts, ingest_time=time.time(), pool=[])

    # Resolved once, not per-thread: whether the last bar is a partial candle is a property
    # of ingest, not of whenever a replay happens to run.
    market_open = is_market_open()
    ingest_time = time.time()

    def _drop_partial(frames: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        if not market_open:
            return frames
        return {t: (df.iloc[:-1] if len(df) > 1 else df) for t, df in frames.items()}

    print(f"\n[INFO] Downloading {cfg.price_history_period} price history for {len(seed.pool)} tickers...")
    prices = _drop_partial(_download_prices(seed.pool, cfg, "Pool prices"))

    # Benchmark + reference universe: the basis for excess-sharpe and the grade cuts.
    ref_tickers = _reference_universe(cfg)
    to_fetch = sorted(set(ref_tickers) | {cfg.benchmark})
    print(f"\n[INFO] Downloading benchmark ({cfg.benchmark}) + {len(ref_tickers)}-ticker reference universe...")
    reference = _drop_partial(_download_prices(to_fetch, cfg, "Reference prices"))
    if cfg.benchmark not in reference:
        print(f"[WARN] Benchmark {cfg.benchmark} unavailable — the whole ladder will be None this run")

    print(f"\n[INFO] Fetching info for {len(seed.pool)} tickers ({cfg.max_workers} workers)...")
    info_raw = _map(lambda t: _fetch_info(t, cfg), seed.pool, cfg.max_workers, "Info fetch")
    info: Dict[str, dict] = {t: v for t, v in info_raw.items() if v}

    # Only spend a news request on tickers that can survive the gate. The gate values go into
    # meta so a replay with looser filters can warn instead of silently scoring news as 0.
    newsworthy = [t for t in seed.pool
                  if t in info and passes_liquidity(info[t], cfg.min_price, cfg.min_avg_volume)]
    print(f"\n[INFO] Fetching news for {len(newsworthy)} tickers that pass the liquidity gate...")

    def _news(t: str) -> list:
        # The company name comes from the info dict already fetched — no extra request. It is
        # what stops AD returning Netflix ad-revenue stories and WRAP returning "Markets Wrap".
        name = info[t].get("shortName") or info[t].get("longName") or ""
        return fetch_news(t, company_name=name, lookback_days=cfg.lookback_days,
                          timeout=cfg.request_timeout)

    news_raw = _map(_news, newsworthy, cfg.max_workers, "News fetch")
    news = {t: (v or []) for t, v in news_raw.items()}

    # StockTwits stream sentiment for the liquid candidates, in confirmation-rank order so the
    # rate-limit budget spends on the most-corroborated names. Sequential + throttled, not
    # threaded: the ~200/hr cap is per-IP, so concurrency would only reach it faster.
    print(f"\n[INFO] Fetching StockTwits stream sentiment "
          f"(budget {cfg.stocktwits_stream_budget}, {len(newsworthy)} candidates)...")
    st_sentiment = fetch_stocktwits_sentiment(cfg, newsworthy)

    # Resolve the finviz P/E fallback here so score_fundamentals stays offline.
    missing_pe = [t for t in newsworthy if info[t].get("trailingPE") is None]
    if missing_pe:
        print(f"[INFO] Resolving finviz P/E fallback for {len(missing_pe)} tickers...")
        for t, pe in _map(lambda x: fetch_finviz_pe(x, cfg.request_timeout),
                          missing_pe, cfg.max_workers, "P/E fallback").items():
            if pe is not None:
                info[t][FINVIZ_PE_KEY] = pe

    return Snapshot(
        run_ts=run_ts,
        ingest_time=ingest_time,
        pool=seed.pool,
        prices=prices,
        reference=reference,
        info=info,
        news=news,
        reddit_counts=seed.reddit_counts,
        reddit_posts=seed.reddit_posts,
        st_ranks=seed.st_ranks,
        st_sentiment=st_sentiment,
        capitol=seed.capitol_trades,
        meta={
            "market_open_at_ingest": market_open,
            "price_history_period": cfg.price_history_period,
            "confirmations": seed.confirmations,
            "ingest_filters": {"min_price": cfg.min_price, "min_avg_volume": cfg.min_avg_volume},
            "news_fetched_for": sorted(news),
            "benchmark": cfg.benchmark,
            "reference_universe": ref_tickers,
            "stocktwits_stream_budget": cfg.stocktwits_stream_budget,
            "stocktwits_sentiment_coverage": len(st_sentiment),
        },
    )
