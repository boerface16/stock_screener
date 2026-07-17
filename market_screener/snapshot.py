"""
Snapshot I/O — ingest writes one, scoring is a pure function of it.

Reproducibility is a precondition for tuning: you cannot A/B two lexicons if re-scoring
requires re-fetching a changed internet. See tasks/lessons.md.

The rule that makes replay exact: anything a scorer reads that is not in the snapshot is a
replay bug. That includes the wall clock — `ingest_time` is recorded here so that
time-relative scorers (news recency, trade recency) resolve against ingest, not against
whenever the replay happens to run.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

# Bump when the on-disk layout changes. load_snapshot refuses mismatches rather than
# guessing at a migration — a silently misread snapshot is worse than no snapshot.
#   v1 -> v2: price history moved 6mo -> max for the ladder; added reference.parquet
#             (benchmark + reference universe closes, the basis for the grade cuts).
#   v2 -> v3: news items carry {title, published} instead of {providerPublishTime} — the
#             relevance filter and the sentiment lexicon both need the headline text.
#   v3 -> v4: stocktwits.json carries {ranks, sentiment}; sentiment is per-ticker Bull/Bear
#             counts from message streams and is now the social_sentiment source (Reddit-title
#             lexicon retired — it covered ~1.5% of the pool).
SCHEMA_VERSION = 4

_PRICES = "prices.parquet"
_REFERENCE = "reference.parquet"
_INFO = "info.json"
_NEWS = "news.json"
_REDDIT = "reddit.json"
_STOCKTWITS = "stocktwits.json"
_CAPITOL = "capitol.json"
_META = "meta.json"


@dataclass
class Snapshot:
    """Every input the scorers are allowed to read."""
    run_ts: str
    ingest_time: float                      # unix seconds; scorers read this, never time.time()
    pool: List[str]                         # deterministic order (see sources.rank_pool)
    prices: Dict[str, pd.DataFrame] = field(default_factory=dict)
    # Benchmark + reference-universe closes. Stored as data rather than as a precomputed cut
    # table so the grade scale stays tunable on replay: recalibration is derived at score time
    # and is still exact, because it derives from bytes on disk instead of a fresh fetch.
    reference: Dict[str, pd.DataFrame] = field(default_factory=dict)
    info: Dict[str, dict] = field(default_factory=dict)
    news: Dict[str, List[dict]] = field(default_factory=dict)
    reddit_counts: Dict[str, int] = field(default_factory=dict)
    reddit_posts: List[dict] = field(default_factory=list)
    st_ranks: Dict[str, int] = field(default_factory=dict)
    st_sentiment: Dict[str, Dict[str, int]] = field(default_factory=dict)  # {ticker: {bull, bear}}
    capitol: Dict[str, dict] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def snapshot_path(cfg, run_ts: str) -> str:
    return os.path.join(cfg.snapshot_dir, run_ts)


def _dump(obj, path: str) -> None:
    # sort_keys so a snapshot of identical data is byte-identical; default=str because
    # yfinance info dicts carry the occasional non-JSON scalar.
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True, indent=1, default=str)


def _load(path: str, fallback):
    if not os.path.exists(path):
        return fallback
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _prices_to_frame(prices: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for ticker in sorted(prices):
        df = prices[ticker]
        if df is None or df.empty:
            continue
        df = df.copy()
        df.index.name = "date"
        df = df.reset_index()
        df.insert(0, "ticker", ticker)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ticker", "date"])
    return pd.concat(frames, ignore_index=True)


def _frame_to_prices(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    if df.empty:
        return out
    for ticker, g in df.groupby("ticker", sort=True):
        g = g.drop(columns=["ticker"]).set_index("date")
        out[str(ticker)] = g
    return out


def write_snapshot(snap: Snapshot, cfg) -> str:
    d = snapshot_path(cfg, snap.run_ts)
    os.makedirs(d, exist_ok=True)

    _prices_to_frame(snap.prices).to_parquet(os.path.join(d, _PRICES), index=False)
    _prices_to_frame(snap.reference).to_parquet(os.path.join(d, _REFERENCE), index=False)
    _dump(snap.info, os.path.join(d, _INFO))
    _dump(snap.news, os.path.join(d, _NEWS))
    _dump({"counts": snap.reddit_counts, "posts": snap.reddit_posts}, os.path.join(d, _REDDIT))
    _dump({"ranks": snap.st_ranks, "sentiment": snap.st_sentiment}, os.path.join(d, _STOCKTWITS))
    _dump(snap.capitol, os.path.join(d, _CAPITOL))

    meta = {
        **snap.meta,
        "schema_version": SCHEMA_VERSION,
        "run_ts": snap.run_ts,
        "ingest_time": snap.ingest_time,
        "pool": snap.pool,
    }
    _dump(meta, os.path.join(d, _META))
    return d


def load_snapshot(cfg, run_ts: str) -> Snapshot:
    d = snapshot_path(cfg, run_ts)
    if not os.path.isdir(d):
        raise FileNotFoundError(f"No snapshot at {d}")

    meta = _load(os.path.join(d, _META), None)
    if meta is None:
        raise FileNotFoundError(f"Snapshot {run_ts} has no {_META}")

    found = meta.get("schema_version")
    if found != SCHEMA_VERSION:
        raise ValueError(
            f"Snapshot {run_ts} is schema v{found}, this build reads v{SCHEMA_VERSION}. "
            f"Re-ingest rather than replaying it — the layout changed."
        )

    def _prices(name: str) -> Dict[str, pd.DataFrame]:
        path = os.path.join(d, name)
        return _frame_to_prices(pd.read_parquet(path)) if os.path.exists(path) else {}

    reddit = _load(os.path.join(d, _REDDIT), {})
    st_blob = _load(os.path.join(d, _STOCKTWITS), {})
    return Snapshot(
        run_ts=meta["run_ts"],
        ingest_time=float(meta["ingest_time"]),
        pool=list(meta.get("pool", [])),
        prices=_prices(_PRICES),
        reference=_prices(_REFERENCE),
        info=_load(os.path.join(d, _INFO), {}),
        news=_load(os.path.join(d, _NEWS), {}),
        reddit_counts={k: int(v) for k, v in reddit.get("counts", {}).items()},
        reddit_posts=reddit.get("posts", []),
        st_ranks={k: int(v) for k, v in st_blob.get("ranks", {}).items()},
        st_sentiment={k: {"bull": int(v.get("bull", 0)), "bear": int(v.get("bear", 0))}
                      for k, v in st_blob.get("sentiment", {}).items()},
        capitol=_load(os.path.join(d, _CAPITOL), {}),
        meta=meta,
    )


def latest_run_ts(cfg) -> Optional[str]:
    root = cfg.snapshot_dir
    if not os.path.isdir(root):
        return None
    runs = sorted(r for r in os.listdir(root) if os.path.isdir(os.path.join(root, r)))
    return runs[-1] if runs else None
