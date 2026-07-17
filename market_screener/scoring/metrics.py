"""
Risk metrics over a close-price series.

All of these are pure numpy over a price array — no clock, no network — so they are safe to
call from the scorer. They match `quantstats` to floating-point noise (see the equivalence
probe in the Phase 2 notes); computing them directly avoids 2,000 quantstats calls per run
(400 tickers x 5 ladder windows) and the matplotlib/seaborn/scipy/tabulate dependency chain.

Deliberately excluded, with the correlations that disqualified them:
  sortino / calmar / omega / profit_factor / cagr  — rho 0.95-1.00 with sharpe
  value_at_risk                                    — rho -1.00 with volatility
  skew / kurtosis / tail_ratio                     — unstable on short windows
"""
from typing import Optional, Sequence

import numpy as np


def daily_returns(closes: Sequence[float]) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < 2:
        return np.empty(0)
    return c[1:] / c[:-1] - 1.0


def sharpe(closes: Sequence[float], periods: int = 252) -> Optional[float]:
    """Annualised Sharpe at rf=0. None when undefined rather than 0.0 — a missing metric must
    stay distinguishable from a measured-and-mediocre one."""
    r = daily_returns(closes)
    if len(r) < 2:
        return None
    sd = r.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return None
    return float(r.mean() / sd * np.sqrt(periods))


def volatility(closes: Sequence[float], periods: int = 252) -> Optional[float]:
    r = daily_returns(closes)
    if len(r) < 2:
        return None
    sd = r.std(ddof=1)
    return float(sd * np.sqrt(periods)) if np.isfinite(sd) else None


def max_drawdown(closes: Sequence[float]) -> Optional[float]:
    """Worst peak-to-trough decline as a negative fraction (-0.35 = -35%)."""
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < 2:
        return None
    peak = np.maximum.accumulate(c)
    return float((c / peak - 1.0).min())


def ulcer_index(closes: Sequence[float]) -> Optional[float]:
    """RMS drawdown — penalises deep *and* long declines, unlike max_drawdown's single point."""
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < 2:
        return None
    peak = np.maximum.accumulate(c)
    dd = (c / peak - 1.0) * 100.0
    return float(np.sqrt(np.mean(dd ** 2)))


def window(closes: Sequence[float], bars: int) -> Optional[np.ndarray]:
    """Last `bars` closes, or None if the series is too short.

    Returning None rather than a shorter slice is load-bearing: a min/mean over 3 windows beats
    one over 4 in expectation, so silently scoring a 2.4-year stock's "10y" window on 2.4 years
    of data would hand short-history names a free advantage — exactly the meme bias the ladder
    exists to expose.
    """
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < bars:
        return None
    return c[-bars:]
