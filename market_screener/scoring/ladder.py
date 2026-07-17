"""
The multi-window ladder: excess sharpe vs the benchmark per window → letter grade → GPA.

Why market-relative and not pool-relative: a pool percentile would make "gold" depend on which
memes got scraped that morning. Excess-vs-SPY is an absolute standard with a real zero, and it
is comparable across runs.

Why the worst window rather than consistency: `-|divergence|` cannot see level — it ranked MSFT
#1 on a -0.66 one-year sharpe, because reliably mediocre maximises consistency.

Why GPA ranks and `worst` only displays: they rank near-identically, so the tiebreak is failure
modes. GPA is unbiased when windows are missing; `worst` is structurally biased toward
short-history names (a min over 3 windows beats a min over 4), which is the exact meme bias the
ladder exists to expose. GPA's weakness — A/A/A/F == B/B/B/B — is a *display* problem, fixed by
shipping `gold_worst` alongside. `worst`'s bias is a *ranking* problem and no extra column fixes it.
"""
from typing import Dict, List, Optional, Sequence

import numpy as np

from scoring.metrics import sharpe, window


def excess_sharpe(
    closes: Sequence[float],
    benchmark_closes: Sequence[float],
    bars: int,
    periods: int = 252,
) -> Optional[float]:
    """sharpe(stock, w) - sharpe(benchmark, w). None if either series is too short.

    Windows are sliced by position on both series. Both end at the ingest date and trade the
    same calendar, so the last N bars cover the same dates; a halted ticker could drift by a
    day or two, which is immaterial next to the metric's own noise.
    """
    s = window(closes, bars)
    b = window(benchmark_closes, bars)
    if s is None or b is None:
        return None
    s_sharpe = sharpe(s, periods)
    b_sharpe = sharpe(b, periods)
    if s_sharpe is None or b_sharpe is None:
        return None
    return s_sharpe - b_sharpe


def ladder_xs(
    closes: Sequence[float],
    benchmark_closes: Sequence[float],
    windows: Dict[str, int],
    periods: int = 252,
) -> Dict[str, Optional[float]]:
    """{window_name: excess sharpe}. Missing windows are None, never 0.0."""
    return {
        name: excess_sharpe(closes, benchmark_closes, bars, periods)
        for name, bars in windows.items()
    }


def build_grade_cuts(
    reference_xs: Dict[str, List[float]],
    quantiles: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    """
    {window: {grade: lower-bound xs}} from the reference universe's own cross-section.

    Per-window, never one pooled table. Pooled cuts were tested and rejected: window dispersion
    differs wildly (3mo sd 1.63 vs 5y sd 0.38), so a pooled table lets the 5y window
    structurally never award below C+ while 3mo hands out F's freely — GPA variance would then
    be driven by the 3-month window on a 2-year tool.
    """
    cuts: Dict[str, Dict[str, float]] = {}
    for win, values in reference_xs.items():
        obs = [v for v in values if v is not None and np.isfinite(v)]
        if len(obs) < 20:      # too thin to define 10 quantiles honestly
            continue
        arr = np.asarray(obs, dtype=float)
        cuts[win] = {g: float(np.quantile(arr, q)) for g, q in quantiles.items()}
    return cuts


def grade_for(xs: Optional[float], window_cuts: Optional[Dict[str, float]]) -> Optional[str]:
    """Letter for one window's excess sharpe. None when ungradeable (no data / no cuts)."""
    if xs is None or window_cuts is None or not np.isfinite(xs):
        return None
    # Best grade whose lower bound the value clears; below them all is an F.
    for grade, lower in sorted(window_cuts.items(), key=lambda kv: -kv[1]):
        if xs >= lower:
            return grade
    return "F"


def grade_ladder(
    xs_by_window: Dict[str, Optional[float]],
    cuts: Dict[str, Dict[str, float]],
) -> Dict[str, Optional[str]]:
    return {win: grade_for(xs, cuts.get(win)) for win, xs in xs_by_window.items()}


def gold_metrics(
    grades: Dict[str, Optional[str]],
    points: Dict[str, float],
    windows_order: Sequence[str],
) -> dict:
    """gold_gpa (ranks), gold_worst + grade string (display), windows_available."""
    earned = [points[g] for g in (grades.get(w) for w in windows_order) if g is not None]
    return {
        "gold_gpa": round(float(np.mean(earned)), 4) if earned else None,
        "gold_worst": round(float(min(earned)), 4) if earned else None,
        "grades": "/".join(grades.get(w) or "-" for w in windows_order),
        "windows_available": len(earned),
    }


def divergence(xs_by_window: Dict[str, Optional[float]], short: str, long: str) -> Optional[float]:
    """Short-window minus long-window excess sharpe.

    Display only. It is NOT a meme detector on its own — its top hit was MET (MetLife), a
    large-cap insurer having a good quarter. `meme_flag` combines it with attention and size.
    """
    a, b = xs_by_window.get(short), xs_by_window.get(long)
    if a is None or b is None:
        return None
    return round(a - b, 4)
