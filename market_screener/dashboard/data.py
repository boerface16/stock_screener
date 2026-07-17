"""
Cached data layer for the dashboard.

The dashboard reads **snapshots, never the CSV**. The CSV is truncated to `--n`
(`screener.py:132`), so it carries 50 rows rather than the ~370 the pool actually scores —
useless as a browsing surface. `load_snapshot` + `score_all` is pure and needs no network,
which is what makes reading the real pool free. That purity is Phase 1's payoff.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from config import Config
from scoring.scorer import composite, filter_reasons, score_all
from snapshot import SCHEMA_VERSION, Snapshot, load_snapshot

# Signals carry a category; these are the display names used everywhere in the UI.
CATEGORY_LABELS = {
    "fundamentals": "Fundamentals",
    "price_risk": "Price / Risk",
    "direction": "Direction",
    "insider": "Insider",
}


def list_runs(cfg: Config) -> List[str]:
    """Schema-compatible snapshot run timestamps, newest first.

    Runs on an older schema are hidden rather than listed-and-then-erroring: load_snapshot refuses
    a mismatch (by design), so offering one in the picker would only produce a crash on select.
    """
    root = cfg.snapshot_dir
    if not os.path.isdir(root):
        return []
    runs = [r for r in os.listdir(root) if os.path.isdir(os.path.join(root, r))]
    return sorted((r for r in runs if _schema_of(root, r) == SCHEMA_VERSION), reverse=True)


def _schema_of(root: str, run: str) -> Optional[int]:
    try:
        with open(os.path.join(root, run, "meta.json"), encoding="utf-8") as f:
            return json.load(f).get("schema_version")
    except (OSError, ValueError):
        return None


def cfg_fingerprint(cfg: Config) -> str:
    """Hash of every knob, so editing config.py invalidates the cached scores.

    Without this, a config change would be invisible behind the cache and the dashboard would
    quietly show numbers the current code no longer produces.
    """
    blob = json.dumps(dataclasses.asdict(cfg), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


@st.cache_resource(show_spinner="Loading snapshot…")
def get_snapshot(run_ts: str) -> Snapshot:
    """cache_resource, not cache_data: a Snapshot holds ~550 DataFrames (~46 MB) and pickling
    it on every call would cost more than the load it is meant to save."""
    return load_snapshot(Config(), run_ts)


@st.cache_data(show_spinner="Scoring the pool — Monte Carlo, ~1-2 min on a cold cache…")
def get_scored(run_ts: str, fingerprint: str) -> List[dict]:
    """The unfiltered cross-section, scored once per (snapshot, config).

    Unfiltered because `coverage` is weight-dependent: the weight sliders move which tickers
    clear `min_coverage`, so filtering here would freeze the default weights' survivors in.
    `fingerprint` is unused in the body — it is the cache key (see cfg_fingerprint).
    """
    return score_all(get_snapshot(run_ts), Config(), apply_filters=False)


def with_weights(cfg: Config, weights: Dict[str, float]) -> Config:
    """A copy of cfg carrying new category weights, renormalized to sum to 1.0.

    Renormalized because `coverage` is defined as the fraction of *total* weight observed and
    is gated by `min_coverage`. Weights summing to 1.2 would inflate every coverage and quietly
    admit tickers the real screener drops.
    """
    total = sum(weights.values())
    if total <= 0:
        return cfg
    return dataclasses.replace(cfg, weights={k: v / total for k, v in weights.items()})


def rescore(rows: List[dict], cfg: Config) -> List[dict]:
    """Re-derive composite + coverage under `cfg`'s weights, from already-scored signals.

    Cheap — a weighted sum over ~370 rows, no Monte Carlo, no re-scoring. It calls the
    production `scorer.composite`; a second renormalization here would be the duplicate-fetcher
    bug from tasks/lessons.md, and it would let the dashboard disagree with the pipeline.
    """
    out = [
        {**r, **composite({k: r.get(k) for k in cfg.signal_weights}, cfg)}
        for r in rows
    ]
    out.sort(key=lambda r: (r["composite_score"] is None,
                            -(r["composite_score"] or 0.0),
                            r["ticker"]))
    return out


def split_filters(rows: List[dict], cfg: Config) -> Tuple[List[dict], List[dict]]:
    """(kept, dropped) under cfg's gates, each dropped row carrying why. Ranks the keepers."""
    kept, dropped = [], []
    for r in rows:
        reasons = filter_reasons(r, cfg)
        if reasons:
            dropped.append({**r, "dropped_for": "; ".join(reasons)})
        else:
            kept.append(r)
    return [{**r, "rank": i + 1} for i, r in enumerate(kept)], dropped


def to_frame(rows: List[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def closes(snap: Snapshot, ticker: str, source: str = "prices") -> Optional[pd.Series]:
    """Close series indexed by date, or None. `source` is "prices" (pool) or "reference" (SPY)."""
    df = getattr(snap, source).get(ticker)
    if df is None or "Close" not in df or df.empty:
        return None
    s = df["Close"].astype(float)
    s.index = pd.to_datetime(s.index)
    return s.dropna()


def signal_stats(rows: List[dict], cfg: Config) -> pd.DataFrame:
    """Health of every ranking signal across the pool: spread, distinct count, saturation.

    tasks/lessons.md: "A signal with no variance is dead, not neutral" — `news` sat constant at
    10.0 and `social` at 0.00 for all 381 rows, both looking like working signals in the output.
    The rule was to check sd / distinct / fraction-pinned on a real pool before trusting a
    signal. This table is that check, standing rather than ad-hoc.
    """
    out = []
    for name in cfg.signal_weights:
        vals = np.array([r[name] for r in rows if r.get(name) is not None], dtype=float)
        n_missing = len(rows) - len(vals)
        if len(vals) == 0:
            out.append({"signal": name, "category": CATEGORY_LABELS[cfg.signal_categories[name]],
                        "weight": _weight_of(name, cfg), "n": 0, "missing": n_missing,
                        "sd": None, "distinct": 0, "at_min": None, "at_max": None,
                        "mean": None, "health": "DEAD — never observed"})
            continue
        sd = float(vals.std())
        distinct = int(len(np.unique(np.round(vals, 4))))
        at_min = float((vals <= vals.min() + 1e-9).mean())
        at_max = float((vals >= vals.max() - 1e-9).mean())
        out.append({
            "signal": name,
            "category": CATEGORY_LABELS[cfg.signal_categories[name]],
            "weight": _weight_of(name, cfg),
            "n": len(vals),
            "missing": n_missing,
            "sd": round(sd, 4),
            "distinct": distinct,
            "at_min": round(at_min, 4),
            "at_max": round(at_max, 4),
            "mean": round(float(vals.mean()), 3),
            "health": _health(sd, distinct, at_min, at_max, n_missing, len(rows)),
        })
    return pd.DataFrame(out)


def _weight_of(name: str, cfg: Config) -> float:
    return round(cfg.weights[cfg.signal_categories[name]] * cfg.signal_weights[name], 4)


def _health(sd: float, distinct: int, at_min: float, at_max: float,
            n_missing: int, n_rows: int) -> str:
    """The thresholds are deliberately blunt — this flags "look at me", it does not adjudicate."""
    if sd < 0.01 or distinct <= 1:
        return "DEAD — no variance, contributes only weight"
    if max(at_min, at_max) > 0.50:
        return f"SATURATED — {max(at_min, at_max):.0%} pinned at one end"
    if n_rows and n_missing / n_rows > 0.90:
        return f"INERT — missing for {n_missing / n_rows:.0%}, renormalizes away"
    if distinct < 10:
        return f"COARSE — only {distinct} distinct values"
    return "ok"
