"""
Cross-sectional percentile scoring.

A hand-picked absolute constant is a fossil the moment its data source changes — `news`
saturating at 8 articles when the feed started returning 100, `max_st_rank=50` when trending
returns 30, growth saturating at +50% when DELL grew 282%. A percentile has no constant to
go stale, so prefer it wherever the signal is a count or a ranking with no meaningful zero.

Use an absolute map instead where a real zero exists (excess-sharpe-vs-SPY, sentiment rate) —
percentiles throw away level, and level is the whole point there.
"""
from bisect import bisect_left, bisect_right
from typing import Dict, Optional, Sequence


def _observed(values: Dict[str, Optional[float]]) -> Dict[str, float]:
    return {k: float(v) for k, v in values.items() if v is not None and v == v}  # v==v drops NaN


def percentile_scores(
    values: Dict[str, Optional[float]],
    higher_is_better: bool = True,
    min_peers: int = 5,
) -> Dict[str, Optional[float]]:
    """
    Map each ticker's value to 0–10 by its mid-rank percentile within the peer group.

    Missing values return None rather than 5.0 — "no data" must stay distinguishable from
    "measured, and average" so it can count against `coverage` instead of masquerading as a
    neutral reading (tasks/lessons.md).

    Returns all-None when fewer than `min_peers` tickers are observed: a percentile over 2
    names is noise wearing a number. Note a peer group of identical values scores everyone
    5.0 — correct, but it means the signal is dead, so check spread before trusting it.
    """
    obs = _observed(values)
    if len(obs) < min_peers:
        return {k: None for k in values}

    ordered = sorted(obs.values())
    n = len(ordered)

    out: Dict[str, Optional[float]] = {}
    for k in values:
        v = obs.get(k)
        if v is None:
            out[k] = None
            continue
        # Mid-rank: ties share one score, and the result is symmetric about 5.0.
        pct = (bisect_left(ordered, v) + bisect_right(ordered, v)) / 2.0 / n
        score = pct * 10.0
        out[k] = round(score if higher_is_better else 10.0 - score, 4)
    return out


def score_against_reference(
    value: Optional[float],
    reference_sorted: Sequence[float],
    higher_is_better: bool = True,
) -> Optional[float]:
    """
    0–10 by position in a FIXED reference distribution rather than the pool's own.

    Pool-relative scoring would make a stock's risk score depend on which memes got scraped
    that morning — the same objection that made the gold metric market-relative. Scoring
    against a stable reference universe keeps the number comparable across runs.
    """
    if value is None or value != value or len(reference_sorted) < 20:
        return None
    n = len(reference_sorted)
    pct = (bisect_left(reference_sorted, value) + bisect_right(reference_sorted, value)) / 2.0 / n
    score = pct * 10.0
    return round(score if higher_is_better else 10.0 - score, 4)


def grouped_percentile_scores(
    values: Dict[str, Optional[float]],
    groups: Dict[str, str],
    higher_is_better: bool = True,
    min_peers: int = 5,
) -> Dict[str, Optional[float]]:
    """
    Percentile within each ticker's group (e.g. sector), falling back to the whole pool when
    a group is too thin. Valuation only means anything against comparable companies, but an
    attention-seeded pool has thin sectors — a 20-row sample had 7 sectors, 4 with ≤2 names.
    """
    pool_wide = percentile_scores(values, higher_is_better, min_peers)

    by_group: Dict[str, Dict[str, Optional[float]]] = {}
    for ticker, value in values.items():
        group = groups.get(ticker)
        if group:
            by_group.setdefault(group, {})[ticker] = value

    out: Dict[str, Optional[float]] = dict(pool_wide)   # ungrouped tickers stay pool-relative
    for members in by_group.values():
        for ticker, score in percentile_scores(members, higher_is_better, min_peers).items():
            # A None here means the group was too thin to rank in — fall back to the pool
            # rather than discarding a value we actually observed.
            if score is not None:
                out[ticker] = score
    return out
