"""Build cohorts from the date-stamped CSVs. Pure — no network, no state.

A *cohort* is one CSV's worth of picks: for every metric bucket, the top-N rows by that metric's
score, each bought at the row's `price_usd` for ~`tracking_position_usd` (floored to whole shares,
minimum 1 so a >$1000 name is still tracked). Direction is always highest score — for
`max_drawdown`/`volatility` the scores are 0-10 with higher = less risk, so "top" is the calmest
names. A row with a missing metric value is simply absent from that bucket (never imputed).
"""
from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

from config import Config


@dataclass(frozen=True)
class Position:
    ticker: str
    entry_price: float      # the CSV's price_usd, frozen at screen time
    shares: int             # floor(position_usd / price), min 1


@dataclass(frozen=True)
class Cohort:
    run_ts: str                             # "20260716_164333" — one per CSV file
    entry_date: date                        # 2026-07-16
    csv_path: str
    buckets: Dict[str, List[Position]]      # metric column -> its top-N positions

    @property
    def tickers(self) -> List[str]:
        """Every distinct ticker held across all buckets in this cohort."""
        return sorted({p.ticker for ps in self.buckets.values() for p in ps})


def list_csvs(cfg: Config) -> List[str]:
    """Every screener CSV under outputs_TA/, oldest first (so cohorts read chronologically)."""
    pattern = os.path.join(cfg.output_dir, "*", "screener_*.csv")
    return sorted(glob.glob(pattern))


def _run_ts(csv_path: str) -> Optional[str]:
    """`.../screener_20260716_164333.csv` -> "20260716_164333", or None if it doesn't parse."""
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    ts = stem.removeprefix("screener_")
    try:
        datetime.strptime(ts, "%Y%m%d_%H%M%S")
    except ValueError:
        return None
    return ts


def _shares(price: float, position_usd: float) -> int:
    return max(1, math.floor(position_usd / price))


def _bucket(df: pd.DataFrame, metric: str, top_n: int, position_usd: float) -> List[Position]:
    """Top-N rows by `metric` (highest first), as sized positions. Rows missing the metric or a
    usable price drop out — a bucket can hold fewer than N."""
    if metric not in df.columns or "price_usd" not in df.columns:
        return []
    sub = df[[metric, "ticker", "price_usd"]].copy()
    sub[metric] = pd.to_numeric(sub[metric], errors="coerce")
    sub["price_usd"] = pd.to_numeric(sub["price_usd"], errors="coerce")
    sub = sub[sub["price_usd"] > 0].dropna(subset=[metric])
    sub = sub.sort_values(metric, ascending=False).head(top_n)
    return [
        Position(ticker=str(r.ticker), entry_price=float(r.price_usd),
                 shares=_shares(float(r.price_usd), position_usd))
        for r in sub.itertuples(index=False)
    ]


def load_cohort(csv_path: str, cfg: Config) -> Optional[Cohort]:
    """One CSV -> one Cohort, or None if the filename/date won't parse or the file is empty."""
    run_ts = _run_ts(csv_path)
    if run_ts is None:
        return None
    try:
        df = pd.read_csv(csv_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return None
    if df.empty or "ticker" not in df.columns:
        return None

    buckets = {
        metric: _bucket(df, metric, top_n, cfg.tracking_position_usd)
        for metric, top_n in cfg.tracking_buckets.items()
    }
    return Cohort(
        run_ts=run_ts,
        entry_date=datetime.strptime(run_ts, "%Y%m%d_%H%M%S").date(),
        csv_path=csv_path,
        buckets=buckets,
    )


def all_cohorts(cfg: Config) -> List[Cohort]:
    """Every parseable cohort on disk, chronological."""
    return [c for c in (load_cohort(p, cfg) for p in list_csvs(cfg)) if c is not None]
