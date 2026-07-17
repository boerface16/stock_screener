"""
Liquidity gate, shared by ingest and scoring.

Ingest uses it to decide which tickers are worth spending a news request on; scoring uses it
to drop rows. One definition, because two copies of a fetcher or a filter drift apart —
see tasks/lessons.md.
"""
from typing import Optional


def _to_float(val) -> Optional[float]:
    """yfinance occasionally returns numbers as strings, or NaN."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f else None  # NaN
    except (ValueError, TypeError):
        return None


def price_of(info: dict) -> float:
    return _to_float(info.get("currentPrice")) or _to_float(info.get("regularMarketPrice")) or 0.0


def avg_volume_of(info: dict) -> int:
    return int(_to_float(info.get("averageVolume")) or 0)


def passes_liquidity(info: dict, min_price: float, min_avg_volume: int) -> bool:
    return price_of(info) >= min_price and avg_volume_of(info) >= min_avg_volume
