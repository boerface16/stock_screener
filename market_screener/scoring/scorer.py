"""
Scoring — a pure function of a Snapshot.

No network, no wall clock, no threads. All three were sources of nondeterminism (see
tasks/lessons.md); if a scorer ever needs something not in the Snapshot, it belongs in ingest.

The taxonomy: attention DISCOVERS, fundamentals SELECT. Yahoo movers / StockTwits / Reddit /
Finviz already decide who is in the pool, so weighting them again in the ranking counts them
twice. Everything attention produces — buzz, rel_volume, momentum — is emitted at weight 0.

Two passes, because percentiles and grade cuts need the peer group before any ticker can be
scored.
"""
from typing import Dict, List, Optional

import numpy as np

from config import Config
from scoring.capitol_hill import score_capitol_hill
from scoring.filters import passes_liquidity, price_of
from scoring.fundamentals import score_fundamentals_pool
from scoring.ladder import build_grade_cuts, divergence, gold_metrics, grade_ladder, ladder_xs
from scoring.metrics import max_drawdown, volatility, window
from scoring.monte_carlo import simulate
from scoring.news import recent_weighted_count
from scoring.percentile import percentile_scores, score_against_reference
from scoring.sentiment import merge_lexicon, score_from_counts, sentiment_score
from scoring.volume import volume_ratio
from snapshot import Snapshot


def _warn_if_looser_than_ingest(snap: Snapshot, cfg: Config) -> None:
    """Ingest only fetched news for tickers that passed its gate. Loosening the gate at
    replay time would silently score those extra tickers as having no news."""
    gate = snap.meta.get("ingest_filters") or {}
    if not gate:
        return
    if cfg.min_price < gate.get("min_price", cfg.min_price) or \
       cfg.min_avg_volume < gate.get("min_avg_volume", cfg.min_avg_volume):
        print(
            f"[WARN] Filters are looser than the snapshot's ingest gate "
            f"(min_price {gate.get('min_price')} → {cfg.min_price}, "
            f"min_avg_volume {gate.get('min_avg_volume')} → {cfg.min_avg_volume}). "
            f"Newly-admitted tickers have no news in this snapshot. Re-ingest to score them."
        )


def _closes(snap: Snapshot, ticker: str, source: str = "prices") -> Optional[np.ndarray]:
    df = getattr(snap, source).get(ticker)
    if df is None or "Close" not in df or df.empty:
        return None
    return df["Close"].to_numpy(dtype=float)


def build_cuts(snap: Snapshot, cfg: Config) -> Dict[str, Dict[str, float]]:
    """Grade cuts from the reference universe's cross-section, recalibrated this run.

    Derived here rather than in ingest so the grade scale stays tunable on replay. Still exact:
    the reference closes live in the snapshot, so the same bytes give the same cuts.
    """
    bench = _closes(snap, cfg.benchmark, "reference")
    if bench is None:
        return {}
    per_window: Dict[str, List[float]] = {w: [] for w in cfg.ladder_windows}
    for ticker in snap.meta.get("reference_universe", []):
        closes = _closes(snap, ticker, "reference")
        if closes is None:
            continue
        for win, xs in ladder_xs(closes, bench, cfg.ladder_windows, cfg.trading_days_per_year).items():
            if xs is not None:
                per_window[win].append(xs)
    return build_grade_cuts(per_window, cfg.grade_quantiles)


def _reference_risk(snap: Snapshot, cfg: Config) -> Dict[str, List[float]]:
    """Sorted max_drawdown / volatility across the reference universe, over the risk window.

    Risk is scored against this fixed cross-section rather than the pool's, so the number means
    the same thing from run to run regardless of what got scraped that morning.
    """
    bars = cfg.ladder_windows[cfg.risk_window]
    dd: List[float] = []
    vol: List[float] = []
    for ticker in snap.meta.get("reference_universe", []):
        closes = _closes(snap, ticker, "reference")
        if closes is None:
            continue
        w = window(closes, bars)
        if w is None:
            continue
        d, v = max_drawdown(w), volatility(w, cfg.trading_days_per_year)
        if d is not None:
            dd.append(d)
        if v is not None:
            vol.append(v)
    return {"max_drawdown": sorted(dd), "volatility": sorted(vol)}


def _risk_metrics(closes: Optional[np.ndarray], cfg: Config) -> Dict[str, Optional[float]]:
    bars = cfg.ladder_windows[cfg.risk_window]
    w = window(closes, bars) if closes is not None else None
    if w is None:
        return {"max_drawdown_raw": None, "volatility_raw": None}
    return {
        "max_drawdown_raw": max_drawdown(w),
        "volatility_raw": volatility(w, cfg.trading_days_per_year),
    }


def composite(signals: Dict[str, Optional[float]], cfg: Config) -> Dict[str, Optional[float]]:
    """
    Weighted mean over the signals actually observed, renormalized per ticker.

    `coverage` falls out as the fraction of total weight that was observed, because the full
    weight set sums to 1.0. A ticker missing half its signals scores on the half it has and
    says so, rather than being handed 5.0s that look like measurements.

    Public because the dashboard's weight sliders re-derive the composite from already-scored
    signals. They must call *this*, not a copy — two implementations of the renormalization
    would drift, which is the duplicate-fetcher bug in tasks/lessons.md.
    """
    num = den = 0.0
    for name, value in signals.items():
        if value is None:
            continue
        w = cfg.weights[cfg.signal_categories[name]] * cfg.signal_weights[name]
        num += w * value
        den += w
    if den == 0:
        return {"composite_score": None, "coverage": 0.0}
    return {"composite_score": round(num / den, 4), "coverage": round(den, 4)}


def filter_reasons(row: dict, cfg: Config) -> List[str]:
    """Every gate this row fails, named. Empty list means it passes.

    Returns reasons rather than a bool so the dashboard can say *why* a ticker was dropped;
    `passes_filters` is just the emptiness of this list, so there is one implementation.
    """
    out: List[str] = []
    if row.get("composite_score") is None:
        out.append("no signals observed")
        return out                      # nothing else is meaningful without a score
    if row["coverage"] < cfg.min_coverage:
        out.append(f"coverage {row['coverage']:.2f} < {cfg.min_coverage}")
    dd = row.get("max_drawdown_raw")
    if dd is not None and dd < cfg.max_drawdown_floor:
        out.append(f"max_drawdown {dd:.2f} < {cfg.max_drawdown_floor}")
    vol = row.get("volatility_raw")
    if vol is not None and vol > cfg.volatility_ceiling:
        out.append(f"volatility {vol:.2f} > {cfg.volatility_ceiling}")
    p_bust = row.get("p_bust_2y")
    if p_bust is not None and p_bust > cfg.mc_bust_filter:
        out.append(f"P(bust) {p_bust:.2f} > {cfg.mc_bust_filter}")
    yrs = row.get("history_years")
    if yrs is not None and yrs < cfg.min_history_years:
        out.append(f"history {yrs:.1f}y < {cfg.min_history_years}y")
    return out


def passes_filters(row: dict, cfg: Config) -> bool:
    """Deterministic gates — the honest version of the noise removal the LLM prompt claimed."""
    return not filter_reasons(row, cfg)


def score_all(snap: Snapshot, cfg: Config, apply_filters: bool = True) -> List[dict]:
    """Score every eligible ticker in the snapshot. Pure: no network, no clock, no threads.

    `apply_filters=False` returns the unfiltered cross-section. The dashboard needs it because
    `coverage` is weight-dependent, so moving a weight slider changes which tickers clear
    `min_coverage` — filtering here would bake in the default weights' survivors.
    """
    _warn_if_looser_than_ingest(snap, cfg)

    bench = _closes(snap, cfg.benchmark, "reference")
    cuts = build_cuts(snap, cfg)
    if not cuts:
        print("[WARN] No grade cuts — reference universe or benchmark missing; ladder is blank.")
    else:
        print(f"[INFO] Grade cuts recalibrated from "
              f"{len(snap.meta.get('reference_universe', []))} reference tickers: "
              + ", ".join(f"{w} A>={c['A']:+.2f}" for w, c in cuts.items()))
    ref_risk = _reference_risk(snap, cfg)

    # --- pass 1: who is eligible, and the cross-sectional inputs -------------------------
    candidates = [
        t for t in snap.pool
        if t in snap.info and passes_liquidity(snap.info[t], cfg.min_price, cfg.min_avg_volume)
    ]
    info_by = {t: snap.info[t] for t in candidates}
    sectors = {t: info.get("sector") for t, info in info_by.items()}
    fundamentals = score_fundamentals_pool(info_by, sectors, cfg.fundamentals_min_peers)

    buzz_raw = {
        t: recent_weighted_count(snap.news.get(t, []), snap.ingest_time, cfg.lookback_days)
        for t in candidates
    }
    news_buzz = percentile_scores(buzz_raw)          # a count → percentile, no constant to rot
    reddit_buzz = percentile_scores({t: float(snap.reddit_counts.get(t, 0)) for t in candidates})

    news_lex = merge_lexicon(cfg.sentiment_lexicon_core, cfg.sentiment_lexicon_news)

    # --- pass 2: per ticker ---------------------------------------------------------------
    results: List[dict] = []
    for ticker in candidates:
        try:
            row = _score_ticker(ticker, snap, cfg, cuts, bench, ref_risk, fundamentals,
                                news_buzz, reddit_buzz, news_lex)
        except Exception as e:
            print(f"[WARN] Scoring failed for {ticker}: {e}")
            continue
        if row is None:
            continue
        if apply_filters and not passes_filters(row, cfg):
            continue
        results.append(row)

    # Ticker is the tiebreak. Sorting on score alone left ties to be resolved by whichever
    # thread finished first, so the same data could rank two ways.
    # The None check only fires when apply_filters=False (an unscorable row is filtered out
    # otherwise); it sorts those last and leaves the filtered path's order untouched.
    results.sort(key=lambda r: (r["composite_score"] is None,
                                -(r["composite_score"] or 0.0),
                                r["ticker"]))
    return results


def _score_ticker(
    ticker: str,
    snap: Snapshot,
    cfg: Config,
    cuts: Dict[str, Dict[str, float]],
    bench: Optional[np.ndarray],
    ref_risk: Dict[str, List[float]],
    fundamentals: Dict[str, Dict[str, Optional[float]]],
    news_buzz: Dict[str, Optional[float]],
    reddit_buzz: Dict[str, Optional[float]],
    news_lex: Dict[str, List[str]],
) -> Optional[dict]:
    info = snap.info[ticker]
    closes = _closes(snap, ticker)
    hist = snap.prices.get(ticker)
    windows = list(cfg.ladder_windows)

    # --- price/risk ---
    xs = ladder_xs(closes, bench, cfg.ladder_windows, cfg.trading_days_per_year) \
        if (closes is not None and bench is not None) else {w: None for w in windows}
    grades = grade_ladder(xs, cuts)
    gold = gold_metrics(grades, cfg.grade_points, windows)
    risk = _risk_metrics(closes, cfg)

    # gold_gpa is on a 4.0 scale; /4*10 is exact and needs no divisor to go stale. This is why
    # the "principled absolute map for xs" question dissolved: xs is mapped by the recalibrated
    # grade cuts, not by a hand-picked constant.
    gpa_score = round(gold["gold_gpa"] / 4.0 * 10.0, 4) if gold["gold_gpa"] is not None else None

    # --- direction ---
    # news_sentiment: lexicon over Google-News headlines (broad pool coverage).
    # social_sentiment: StockTwits Bull/Bear labels — poster-set, so counted, not lexicon-scored.
    # Reddit was retired from this path (it labeled ~1.5% of the pool); it now feeds buzz only.
    news_titles = [n.get("title", "") for n in snap.news.get(ticker, [])]
    news_sent = sentiment_score(news_titles, news_lex["positive"], news_lex["negative"],
                                cfg.sentiment_shrinkage_k)
    st_sent = snap.st_sentiment.get(ticker)
    social_sent = (score_from_counts(st_sent["bull"], st_sent["bear"], cfg.sentiment_shrinkage_k)
                   if st_sent else None)

    signals: Dict[str, Optional[float]] = {
        "value": fundamentals[ticker]["value"],
        "quality": fundamentals[ticker]["quality"],
        "growth": fundamentals[ticker]["growth"],
        "gold_score": gpa_score,
        "max_drawdown": score_against_reference(risk["max_drawdown_raw"],
                                                ref_risk["max_drawdown"], higher_is_better=True),
        "volatility": score_against_reference(risk["volatility_raw"],
                                              ref_risk["volatility"], higher_is_better=False),
        "news_sentiment": news_sent,
        "social_sentiment": social_sent,
        "capitol_hill": score_capitol_hill(ticker, snap.capitol,
                                            cfg.capitol_buy_points, cfg.capitol_sell_points),
    }

    mc = simulate(closes, cfg.mc_horizon_days, cfg.mc_sims, cfg.mc_goal, cfg.mc_bust,
                  cfg.mc_seed) if closes is not None else None

    # A display key that collides with a ranking-signal key would silently overwrite the value
    # the composite was computed from, so the row would disagree with its own score. This bit
    # already once: `gold` carries a 0-4 gold_gpa while the signal is a 0-10 gold_score.
    collisions = set(signals) & set(gold)
    if collisions:
        raise ValueError(f"display keys collide with ranking signals: {sorted(collisions)}")

    history_years = round(len(closes) / cfg.trading_days_per_year, 2) if closes is not None else None
    row: Dict[str, object] = {
        "ticker": ticker,
        **composite(signals, cfg),
        # --- ranking signals ---
        **{k: v for k, v in signals.items()},
        # --- display only (weight 0) ---
        **gold,
        **{f"xs_{w}": (round(v, 4) if v is not None else None) for w, v in xs.items()},
        "history_years": history_years,
        "divergence": divergence(xs, windows[0], windows[-2] if len(windows) > 1 else windows[0]),
        "news_buzz": news_buzz.get(ticker),
        "social_buzz": reddit_buzz.get(ticker),
        "rel_volume": volume_ratio(hist, cfg.volume_avg_window),
        "max_drawdown_raw": (round(risk["max_drawdown_raw"], 4)
                             if risk["max_drawdown_raw"] is not None else None),
        "volatility_raw": (round(risk["volatility_raw"], 4)
                           if risk["volatility_raw"] is not None else None),
        "p_goal_2y": round(mc["p_goal"], 4) if mc else None,
        "p_bust_2y": round(mc["p_bust"], 4) if mc else None,
        "mc_confidence": round(mc["confidence"], 4) if mc else None,
        "price_usd": round(price_of(info), 4),
        "sector": info.get("sector") or "",
    }
    row["meme_flag"] = _meme_flag(row, info, cfg)
    return row


def _meme_flag(row: dict, info: dict, cfg: Config) -> bool:
    """High divergence AND high attention AND (small cap OR short history).

    Divergence alone is not a meme detector — its top hit was MET (MetLife), a large-cap
    insurer having a good quarter. It takes all three legs.
    """
    div = row.get("divergence")
    buzz = row.get("social_buzz")
    if div is None or buzz is None:
        return False
    cap = info.get("marketCap") or 0
    yrs = row.get("history_years")
    small_or_new = (cap and cap < 2e9) or (yrs is not None and yrs < 3.0)
    return bool(div > 1.0 and buzz >= 8.0 and small_or_new)
