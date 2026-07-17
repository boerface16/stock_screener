"""Turn cohorts + cached prices into the three views the tracking tab shows. Network-free: it is
handed a `{ticker: close-series}` map, so it is pure and testable.

Three deliberately different return measures, because they answer different questions:

  * **Live P/L** — `shares * (latest_close - entry_price)`, using the CSV `price_usd` as the cost
    basis (the locked decision: that's what you "paid"). Answers "how is my paper money doing?"
  * **Fixed-horizon return** — `close(entry + N days) / close(entry) - 1`, anchored on the *same*
    yfinance adjusted series at both ends (never mixing raw CSV price with adjusted closes). This
    is the clean, apples-to-apples number, so it is what ranks the metrics.
  * **Synthetic daily series** — a bucket's daily return = equal-weight mean of the daily returns
    of every position open that day. Compounded into a NAV that feeds the quantstats tearsheet.

A position's entry trading day is the first bar on/after its `entry_date` (so a weekend screen
enters at the next open). A horizon is "not reached yet" when the series lacks enough bars after
entry — those cohorts are excluded from that horizon rather than counted as zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config import Config
from tracking.cohorts import Cohort, Position


# ---------------------------------------------------------------- position-level primitives

def _entry_pos(series: pd.Series, entry_date) -> Optional[int]:
    """Index of the first bar on/after `entry_date`, or None if the series ends before it."""
    i = int(series.index.searchsorted(pd.Timestamp(entry_date)))
    return i if i < len(series) else None


def _asof(series: pd.Series, when: pd.Timestamp) -> Optional[float]:
    """Last close on/before `when`, or None if `when` predates the series."""
    s = series[series.index <= when]
    return float(s.iloc[-1]) if len(s) else None


@dataclass
class PositionResult:
    ticker: str
    entry_date: object
    shares: int
    entry_price: float          # CSV cost basis
    current_close: Optional[float]
    live_pct: Optional[float]   # current_close / entry_price - 1
    live_pnl: Optional[float]   # shares * (current_close - entry_price)
    priced: bool                # False when yfinance has no bar on/after entry


def position_result(pos: Position, entry_date, series: Optional[pd.Series]) -> PositionResult:
    if series is None or series.empty or _entry_pos(series, entry_date) is None:
        return PositionResult(pos.ticker, entry_date, pos.shares, pos.entry_price,
                              None, None, None, priced=False)
    cur = float(series.iloc[-1])
    return PositionResult(
        ticker=pos.ticker, entry_date=entry_date, shares=pos.shares, entry_price=pos.entry_price,
        current_close=cur, live_pct=cur / pos.entry_price - 1.0,
        live_pnl=pos.shares * (cur - pos.entry_price), priced=True,
    )


def horizon_return(pos: Position, entry_date, series: Optional[pd.Series],
                   horizon_bars: int) -> Optional[float]:
    """Total return from entry to entry+N trading days, yf-on-yf. None if too young or unpriced."""
    if series is None or series.empty:
        return None
    p0 = _entry_pos(series, entry_date)
    if p0 is None or p0 + horizon_bars >= len(series):
        return None
    return float(series.iloc[p0 + horizon_bars] / series.iloc[p0] - 1.0)


def _bench_return(bench: Optional[pd.Series], start: pd.Timestamp,
                  bars: int, series_for_dates: pd.Series) -> Optional[float]:
    """SPY's return over the SAME calendar window a position's horizon spans, for excess-vs-SPY."""
    if bench is None or bench.empty:
        return None
    p0 = _entry_pos(series_for_dates, start)
    if p0 is None or p0 + bars >= len(series_for_dates):
        return None
    d0, d1 = series_for_dates.index[p0], series_for_dates.index[p0 + bars]
    c0, c1 = _asof(bench, d0), _asof(bench, d1)
    return (c1 / c0 - 1.0) if (c0 and c1) else None


# ---------------------------------------------------------------- bucket synthetic return series

def bucket_positions(cohorts: List[Cohort], metric: str) -> List[tuple]:
    """Every (entry_date, Position) this metric bucket has held across all cohorts."""
    return [(c.entry_date, p) for c in cohorts for p in c.buckets.get(metric, [])]


def synthetic_returns(cohorts: List[Cohort], metric: str,
                      closes: Dict[str, pd.Series]) -> pd.Series:
    """Bucket's daily return series: equal-weight mean of the daily returns of every position open
    that day. A position contributes from the day AFTER its entry until its data ends."""
    cols = []
    for entry_date, pos in bucket_positions(cohorts, metric):
        s = closes.get(pos.ticker)
        if s is None or s.empty:
            continue
        p0 = _entry_pos(s, entry_date)
        if p0 is None:
            continue
        held = s.iloc[p0:]                      # from entry bar forward
        cols.append(held.pct_change().iloc[1:])  # first bar has no prior -> drop
    if not cols:
        return pd.Series(dtype=float)
    frame = pd.concat(cols, axis=1)
    return frame.mean(axis=1, skipna=True).sort_index()


def nav(returns: pd.Series, base: float = 100.0) -> pd.Series:
    """Compound a daily-return series into a NAV/equity curve. This is the vehicle fed to the
    tearsheet as 'prices' — quantstats pct_changes it straight back to returns, so the library
    still receives RETURNS (never prices; see dashboard/tearsheet.py)."""
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    return base * (1.0 + returns.fillna(0.0)).cumprod()


# ---------------------------------------------------------------- leaderboard

@dataclass
class BucketSummary:
    metric: str
    n_positions: int            # total positions priced across cohorts
    invested: float             # sum of shares * entry_price
    live_value: float           # sum of shares * current_close
    live_pnl: float
    live_pct: Optional[float]   # equal-weight avg of position live %
    horizons: Dict[str, Optional[float]]        # avg forward return per horizon
    horizons_excess: Dict[str, Optional[float]]  # avg (position - SPY) per horizon
    horizon_n: Dict[str, int]                    # cohorts eligible per horizon


def bucket_summary(cohorts: List[Cohort], metric: str, closes: Dict[str, pd.Series],
                   bench: Optional[pd.Series], cfg: Config) -> BucketSummary:
    positions = bucket_positions(cohorts, metric)
    results = [position_result(p, d, closes.get(p.ticker)) for d, p in positions]
    priced = [r for r in results if r.priced]

    invested = sum(r.shares * r.entry_price for r in priced)
    live_value = sum(r.shares * (r.current_close or 0.0) for r in priced)
    live_pnl = sum(r.live_pnl for r in priced if r.live_pnl is not None)
    live_pcts = [r.live_pct for r in priced if r.live_pct is not None]

    horizons, horizons_excess, horizon_n = {}, {}, {}
    for name, bars in cfg.tracking_horizons.items():
        rets, excess = [], []
        for entry_date, pos in positions:
            s = closes.get(pos.ticker)
            hr = horizon_return(pos, entry_date, s, bars)
            if hr is None:
                continue
            rets.append(hr)
            br = _bench_return(bench, pd.Timestamp(entry_date), bars, s)
            if br is not None:
                excess.append(hr - br)
        horizons[name] = float(np.mean(rets)) if rets else None
        horizons_excess[name] = float(np.mean(excess)) if excess else None
        horizon_n[name] = len(rets)

    return BucketSummary(
        metric=metric, n_positions=len(priced), invested=invested, live_value=live_value,
        live_pnl=live_pnl,
        live_pct=float(np.mean(live_pcts)) if live_pcts else None,
        horizons=horizons, horizons_excess=horizons_excess, horizon_n=horizon_n,
    )


def leaderboard(cohorts: List[Cohort], closes: Dict[str, pd.Series],
                bench: Optional[pd.Series], cfg: Config) -> List[BucketSummary]:
    return [bucket_summary(cohorts, m, closes, bench, cfg) for m in cfg.tracking_buckets]


def equity_curves(cohorts: List[Cohort], closes: Dict[str, pd.Series],
                  bench: Optional[pd.Series], cfg: Config) -> pd.DataFrame:
    """One NAV column per bucket plus SPY, on a shared date index — for the comparison chart."""
    curves = {m: nav(synthetic_returns(cohorts, m, closes)) for m in cfg.tracking_buckets}
    curves = {m: s for m, s in curves.items() if not s.empty}
    if not curves:
        return pd.DataFrame()
    frame = pd.DataFrame(curves).sort_index()
    if bench is not None and not bench.empty:
        span = bench[(bench.index >= frame.index.min()) & (bench.index <= frame.index.max())]
        if not span.empty:
            frame["SPY"] = nav(span.pct_change())
    return frame.ffill()


def all_tickers(cohorts: List[Cohort], cfg: Config) -> List[str]:
    return sorted({p.ticker for c in cohorts for p in
                   (q for ps in c.buckets.values() for q in ps)})


def earliest_entry(cohorts: List[Cohort]):
    return min((c.entry_date for c in cohorts), default=None)
