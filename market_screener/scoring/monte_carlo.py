"""
Bootstrap Monte Carlo over the holding period. Display + filter only — never the composite.

Why not quantstats.stats.montecarlo: it *permutes* returns, and prod(1+r) is
permutation-invariant, so every simulation lands on an identical terminal value (measured std
4.9e-15) and `goal_probability` collapses to a binary 0/1 restatement of `trailing_return >=
goal`. Its horizon is also locked to the input length. Bootstrapping *with replacement* is what
makes the paths actually differ.

Why it is excluded from the composite: P(goal) is rho +0.98 with sharpe and P(bust) is rho +0.94
with volatility. They are sharpe and volatility wearing a percentage costume, and adding them
would double-count the ladder — the same mistake that disqualified the sharpe aliases.

Why bust is terminal-based rather than max-drawdown-based: P(maxdd <= -20%) is 0.96-1.00 for 19
of 20 names — saturated, and a saturated signal ranks nothing.
"""
from typing import Dict, Optional, Sequence

import numpy as np

from scoring.metrics import daily_returns


def simulate(
    closes: Sequence[float],
    horizon_days: int,
    n_sims: int,
    goal: float,
    bust: float,
    seed: int,
) -> Optional[Dict[str, float]]:
    """
    Bootstrap terminal returns over `horizon_days`. Fixed seed → identical output on replay.

    Returns p_goal / p_bust / median_return, plus `confidence` derived from drift uncertainty.
    """
    r = daily_returns(closes)
    if len(r) < 60:
        return None

    rng = np.random.default_rng(seed)
    draws = rng.choice(r, size=(n_sims, horizon_days), replace=True)
    terminal = np.prod(1.0 + draws, axis=1) - 1.0

    return {
        "p_goal": float((terminal >= goal).mean()),
        "p_bust": float((terminal <= bust).mean()),
        "median_return": float(np.median(terminal)),
        "confidence": _drift_confidence(r, horizon_days),
    }


def _drift_confidence(returns: np.ndarray, horizon_days: int) -> float:
    """
    0–1 confidence in the P(goal) estimate, from the standard error of the mean return.

    This exists because the headline probability is far less certain than it looks: measured
    P(goal) swings 53-68 points across +/-1 SE of drift (NVDA: 57%, band 20-88%). Volatility
    converges with more data; mean return does not. Reporting P(goal) without this would be
    reporting a number whose error bar is wider than its range.
    """
    n = len(returns)
    se = returns.std(ddof=1) / np.sqrt(n)
    # Drift uncertainty over the horizon, expressed against the horizon's own volatility.
    drift_band = se * horizon_days
    horizon_vol = returns.std(ddof=1) * np.sqrt(horizon_days)
    if horizon_vol == 0 or not np.isfinite(horizon_vol):
        return 0.0
    return round(float(max(0.0, 1.0 - drift_band / horizon_vol)), 4)
