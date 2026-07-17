"""Tracking tab — which metric's picks actually make money.

Reads the date-stamped CSVs (not snapshots — this is the one view built on the CSV artifacts),
turns each into a frozen cohort, prices them from yfinance, and shows three things:
a leaderboard ranked by fixed-horizon excess-vs-SPY, a comparison equity curve, and a per-bucket
drill-down that reuses the ticker tearsheet machinery on the bucket's synthetic strategy.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
import streamlit as st

from config import Config
from dashboard import tearsheet
from tracking import cohorts as cohorts_mod
from tracking import prices, returns

# Nice labels for the metric columns; anything unmapped falls back to the raw name.
_LABELS = {
    "composite_score": "Composite", "value": "Value", "quality": "Quality", "growth": "Growth",
    "gold_score": "Gold (ladder)", "max_drawdown": "Max drawdown", "volatility": "Volatility",
    "news_sentiment": "News", "social_sentiment": "Social", "capitol_hill": "Capitol Hill",
}


def _label(metric: str) -> str:
    return _LABELS.get(metric, metric)


@st.cache_data(show_spinner="Pricing cohorts from yfinance…", ttl=3600)
def _load(cfg_fingerprint: str, n_csvs: int):
    """Cohorts + a {ticker: closes} map + SPY. Keyed on the CSV count so a new run refreshes it;
    ttl caps how long a stale price cache is served. Returns plain objects (cache_data-safe)."""
    cfg = Config()
    cs = cohorts_mod.all_cohorts(cfg)
    tix = returns.all_tickers(cs, cfg)
    start = returns.earliest_entry(cs)
    closes = prices.get_many(cfg, tix, start=start)
    bench = prices.benchmark_closes(cfg, start=start)
    return cs, closes, bench


def render(cfg: Config, cfg_fingerprint: str) -> None:
    st.subheader("Tracking — which metric leads to the best returns")
    csvs = cohorts_mod.list_csvs(cfg)
    if not csvs:
        st.info(
            "No screener CSVs under `outputs_TA/` yet. Each `python screener.py` run writes one; "
            "this tab paper-trades their top picks per metric and follows the returns forward."
        )
        return

    cs, closes, bench = _load(cfg_fingerprint, len(csvs))
    if st.button("↻ Refresh prices", help="Re-pull the latest closes from yfinance."):
        _load.clear()
        st.rerun()

    span = f"{cs[0].entry_date} → today" if cs else "—"
    st.caption(
        f"**{len(cs)}** cohorts (one per CSV) since **{cs[0].entry_date}** · "
        f"**{len(closes)}** tickers priced · benchmark **SPY**. "
        "Each cohort buys that run's top picks at its `price_usd` (~$1000 each, whole shares) and "
        "holds — no selling. Metrics are ranked by forward return vs SPY, not raw P/L."
    )

    lb = returns.leaderboard(cs, closes, bench, cfg)
    rank_h = _ranking_horizon(lb, cfg)
    _leaderboard_table(lb, cfg, rank_h)
    st.divider()
    _comparison_chart(cs, closes, bench, cfg, lb, rank_h)
    st.divider()
    _drilldown(cs, closes, bench, cfg)


# ---------------------------------------------------------------- leaderboard

def _ranking_horizon(lb, cfg: Config) -> Optional[str]:
    """The shortest horizon any bucket has reached — the fairest basis available so far. None
    means no cohort is even a month old yet, so we fall back to live mark-to-market."""
    for name in cfg.tracking_horizons:
        if any(b.horizon_n.get(name, 0) > 0 for b in lb):
            return name
    return None


def _leaderboard_table(lb, cfg: Config, rank_h: Optional[str]) -> None:
    rows = []
    for b in lb:
        row = {
            "Metric": _label(b.metric),
            "Positions": b.n_positions,
            "Invested": b.invested,
            "Live P/L $": b.live_pnl,
            "Live %": b.live_pct,
        }
        for name in cfg.tracking_horizons:
            row[f"{name}"] = b.horizons.get(name)
            row[f"{name} vs SPY"] = b.horizons_excess.get(name)
        row["_sort"] = (b.horizons_excess.get(rank_h) if rank_h else b.live_pct)
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values("_sort", ascending=False, na_position="last").drop(columns="_sort")
    df.insert(0, "Rank", range(1, len(df) + 1))

    basis = (f"**{rank_h} return vs SPY**" if rank_h
             else "**live % return** (no cohort has reached 1 month yet — live standings for now)")
    st.markdown(f"#### Leaderboard — ranked by {basis}")

    pct_cols = ["Live %"] + [c for c in df.columns if c in cfg.tracking_horizons
                             or c.endswith("vs SPY")]
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "Invested": st.column_config.NumberColumn(format="$%.0f"),
            "Live P/L $": st.column_config.NumberColumn(format="$%.0f"),
            **{c: st.column_config.NumberColumn(format="percent") for c in pct_cols},
        },
    )
    st.caption(
        "Live columns mark every open position at today's price using the CSV cost basis. Horizon "
        "columns are the average forward return of cohorts old enough to have reached that horizon "
        "(younger cohorts are excluded, not counted as zero) — so early on most are blank."
    )


# ---------------------------------------------------------------- comparison chart

def _comparison_chart(cs, closes, bench, cfg: Config, lb, rank_h: Optional[str]) -> None:
    st.markdown("#### Equity curves")
    frame = returns.equity_curves(cs, closes, bench, cfg)
    if frame.empty or len(frame) < 2:
        st.info("Need at least two trading days of history to chart. Come back after the next run.")
        return

    # Default to SPY + the top 3 buckets by the ranking basis, keeps the chart readable.
    ranked = sorted(lb, key=lambda b: ((b.horizons_excess.get(rank_h) if rank_h else b.live_pct)
                                       or float("-inf")), reverse=True)
    default = [b.metric for b in ranked[:3]]
    options = [m for m in cfg.tracking_buckets if m in frame.columns]
    picked = st.multiselect(
        "Buckets to plot (SPY always shown)", options, default=[m for m in default if m in options],
        format_func=_label,
    )
    cols = [c for c in picked if c in frame.columns]
    if "SPY" in frame.columns:
        cols = cols + ["SPY"]
    chart = frame[cols].rename(columns={m: _label(m) for m in picked})
    st.line_chart(chart, height=380)
    st.caption("Each line is a bucket's synthetic strategy — $100 start, equal-weight of whatever "
               "positions are open each day, held from entry. SPY over the same span for reference.")


# ---------------------------------------------------------------- per-bucket drill-down

def _drilldown(cs, closes, bench, cfg: Config) -> None:
    st.markdown("#### Per-bucket detail")
    metric = st.selectbox("Bucket", list(cfg.tracking_buckets), format_func=_label)

    sr = returns.synthetic_returns(cs, metric, closes)
    navs = returns.nav(sr)
    if bench is not None and not bench.empty and len(navs):
        span = bench[(bench.index >= navs.index.min()) & (bench.index <= navs.index.max())]
        bench_nav = returns.nav(span.pct_change()) if not span.empty else None
    else:
        bench_nav = None

    if len(navs) < 3 or bench_nav is None or len(bench_nav) < 3:
        st.info("Not enough history for a full tearsheet yet — it needs a few weeks of trading "
                "days. The picks and live P/L below are already live.")
    else:
        run_ts = cs[-1].run_ts       # newest cohort — cache key; any new run refreshes the report
        html = tearsheet.build_html(f"track_{run_ts}", _label(metric), "all", navs, bench_nav)
        if html and not html.startswith("__ERROR__"):
            import streamlit.components.v1 as components
            components.html(html, height=900, scrolling=True)
        elif html and html.startswith("__ERROR__"):
            st.warning(f"Tearsheet failed: {html[9:]}")

    _picks_table(cs, closes, metric, cfg)


def _picks_table(cs, closes, metric: str, cfg: Config) -> None:
    rows = []
    for c in cs:
        for p in c.buckets.get(metric, []):
            r = returns.position_result(p, c.entry_date, closes.get(p.ticker))
            rows.append({
                "Cohort": str(c.entry_date), "Ticker": p.ticker, "Shares": p.shares,
                "Entry $": p.entry_price,
                "Now $": r.current_close, "Live %": r.live_pct, "P/L $": r.live_pnl,
            })
    if not rows:
        st.write("No picks in this bucket yet.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "Entry $": st.column_config.NumberColumn(format="$%.2f"),
            "Now $": st.column_config.NumberColumn(format="$%.2f"),
            "P/L $": st.column_config.NumberColumn(format="$%.0f"),
            "Live %": st.column_config.NumberColumn(format="percent"),
        },
    )
