"""
Fundamentals: value, quality, growth — each a sector-relative percentile.

Percentiles, not absolute thresholds. Every previous mapping here was a hand-picked constant
that had already gone stale: growth saturated at +50% while DELL grew 282%, and P/E used a
fixed 10/20/40 ladder that means something different in software than in utilities. A
percentile has no constant to rot (tasks/lessons.md).

Sector-relative because valuation only means anything against comparable companies. Measured
on a real 400-ticker pool: 11 sectors, thinnest 9 names, 0% below min_peers — so the sector
peer group is genuinely available, not a theoretical nicety.

Missing values are excluded from the percentile and counted against `coverage`. They are never
imputed to 5.0: "no data" must stay distinguishable from "measured, and average".
"""
from typing import Dict, List, Optional, Tuple

from scoring.percentile import grouped_percentile_scores

# Ingest writes the finviz P/E fallback into `info` under this key so scoring stays offline.
FINVIZ_PE_KEY = "_finviz_trailingPE"


def fetch_finviz_pe(ticker: str, timeout: int = 10) -> Optional[float]:
    """Network. Called by ingest only — never at score time. yfinance P/E coverage is ~75%."""
    try:
        from finviz.screener import Screener
        for stock in Screener(tickers=[ticker], table="Valuation"):
            pe_str = stock.get("P/E", "-")
            if pe_str and pe_str != "-":
                return float(pe_str)
    except Exception:
        pass
    return None

# (info key, higher_is_better, must_be_positive)
# must_be_positive marks ratios that are meaningless at or below zero rather than merely bad:
# a loss-making company has no interpretable P/E, and ranking it as "cheap" would be a lie.
# That is the negative-earnings guard, and the same logic covers DELL's -188.79 book value.
_VALUE: List[Tuple[str, bool, bool]] = [
    ("trailingPE", False, True),
    ("priceToSalesTrailing12Months", False, True),
    ("enterpriseToEbitda", False, True),
]
_QUALITY: List[Tuple[str, bool, bool]] = [
    ("profitMargins", True, False),      # negative margins are meaningful, keep them
    ("returnOnEquity", True, False),
    ("debtToEquity", False, False),
    ("currentRatio", True, True),
]
_GROWTH: List[Tuple[str, bool, bool]] = [
    ("revenueGrowth", True, False),
    ("earningsGrowth", True, False),
]

CATEGORIES: Dict[str, List[Tuple[str, bool, bool]]] = {
    "value": _VALUE,
    "quality": _QUALITY,
    "growth": _GROWTH,
}
FIELD_COUNT = sum(len(v) for v in CATEGORIES.values())


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f else None  # NaN
    except (ValueError, TypeError):
        return None


def _extract(info: dict, key: str, must_be_positive: bool) -> Optional[float]:
    v = _to_float(info.get(key))
    if v is None and key == "trailingPE":
        v = _to_float(info.get(FINVIZ_PE_KEY))   # resolved by ingest; P/E coverage is only ~75%
    if v is None:
        return None
    if must_be_positive and v <= 0:
        return None
    return v


def fundamentals_coverage(info: dict) -> float:
    """Fraction of the 9 underlying fields actually observed for this ticker."""
    seen = sum(
        1
        for fields in CATEGORIES.values()
        for key, _, pos in fields
        if _extract(info, key, pos) is not None
    )
    return round(seen / FIELD_COUNT, 4)


def score_fundamentals_pool(
    info_by_ticker: Dict[str, dict],
    sectors: Dict[str, Optional[str]],
    min_peers: int = 5,
) -> Dict[str, Dict[str, Optional[float]]]:
    """
    {ticker: {"value": 0-10|None, "quality": ..., "growth": ..., "coverage": 0-1}}

    Cross-sectional by construction — a percentile needs the peer group, so this cannot be a
    per-ticker function.
    """
    out: Dict[str, Dict[str, Optional[float]]] = {t: {} for t in info_by_ticker}

    for category, fields in CATEGORIES.items():
        scored_fields = []
        for key, higher_is_better, must_be_positive in fields:
            raw = {t: _extract(info, key, must_be_positive) for t, info in info_by_ticker.items()}
            scored_fields.append(
                grouped_percentile_scores(raw, sectors, higher_is_better=higher_is_better,
                                          min_peers=min_peers)
            )
        # Average the sub-metrics each ticker actually has, rather than penalising a missing one.
        for ticker in out:
            vals = [s[ticker] for s in scored_fields if s.get(ticker) is not None]
            out[ticker][category] = round(sum(vals) / len(vals), 4) if vals else None

    for ticker, info in info_by_ticker.items():
        out[ticker]["coverage"] = fundamentals_coverage(info)
    return out
