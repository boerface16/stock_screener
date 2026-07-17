"""Per-ticker detail — the ladder, the signal breakdown, the Monte Carlo, and the tearsheet."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from config import Config
from dashboard import data, tearsheet
from scoring.monte_carlo import simulate_terminal
from scoring.reason import build_reason
from snapshot import Snapshot


def render(rows: List[dict], snap: Snapshot, cfg: Config, run_ts: str) -> None:
    st.subheader("Ticker detail")
    if not rows:
        st.warning("Nothing scored in this snapshot.")
        return

    by_ticker = {r["ticker"]: r for r in rows}
    tickers = sorted(by_ticker)

    # Type-to-search: filter the list by substring before the dropdown, so you can jump straight
    # to a ticker instead of scrolling ~400 names. Empty search = the full list.
    query = st.text_input("Search ticker", "", placeholder="e.g. NVDA").strip().upper()
    matches = [t for t in tickers if query in t] if query else tickers
    if not matches:
        st.warning(f"No ticker matches “{query}”.")
        return

    default = st.session_state.get("selected_ticker")
    idx = matches.index(default) if default in matches else 0
    ticker = st.selectbox("Ticker", matches, index=idx, key="ticker_pick")
    st.session_state["selected_ticker"] = ticker

    row = by_ticker[ticker]
    _header(row, cfg)
    st.divider()

    left, right = st.columns([1, 1])
    with left:
        _ladder(row, cfg)
    with right:
        _signals(row, rows, cfg)

    st.divider()
    _monte_carlo(row, snap, cfg, ticker)
    st.divider()
    _tearsheet(snap, cfg, ticker, run_ts)


def _header(row: dict, cfg: Config) -> None:
    c = st.columns(5)
    c[0].metric("Rank", row.get("rank", "—"))
    c[1].metric("Composite", f"{row['composite_score']:.2f}"
                if row.get("composite_score") is not None else "—")
    c[2].metric("Coverage", f"{row.get('coverage', 0):.0%}")
    c[3].metric("Price", f"${row.get('price_usd', 0):,.2f}")
    c[4].metric("Sector", row.get("sector") or "—")
    st.info(build_reason(row, cfg))
    if row.get("meme_flag"):
        st.warning(
            "**Meme flag** — high divergence *and* high attention *and* (small cap or short "
            "history). Divergence alone is not a meme detector: its top hit was MetLife."
        )


def _ladder(row: dict, cfg: Config) -> None:
    st.markdown("**Grade ladder** — excess sharpe vs SPY, per window")
    windows = list(cfg.ladder_windows)
    grades = (row.get("grades") or "").split("/")
    frame = pd.DataFrame({
        "window": windows,
        "excess sharpe": [row.get(f"xs_{w}") for w in windows],
        "grade": [grades[i] if i < len(grades) else "—" for i in range(len(windows))],
    })
    st.dataframe(frame, hide_index=True, width="stretch",
                 column_config={"excess sharpe": st.column_config.NumberColumn(format="%+.2f")})

    xs = [row.get(f"xs_{w}") for w in windows]
    if any(v is not None for v in xs):
        chart = pd.DataFrame({"excess sharpe vs SPY": xs}, index=windows)
        st.bar_chart(chart, height=200)

    c = st.columns(3)
    c[0].metric("GPA", f"{row['gold_gpa']:.2f}" if row.get("gold_gpa") is not None else "—",
                help="0-4 report card. GPA ranks; `worst` is display only.")
    c[1].metric("Worst window", f"{row['gold_worst']:.1f}"
                if row.get("gold_worst") is not None else "—")
    c[2].metric("Windows", f"{row.get('windows_available', 0)}/{len(windows)}",
                help=f"{row.get('history_years', 0):.1f}y of history")
    st.caption(
        "`xs = 0` means it merely matched SPY — which still beats **87%** of the S&P 500's own "
        "constituents, because index returns come from a minority of winners. Grades are "
        "norm-referenced against the reference universe and recalibrated every run."
    )


def _signals(row: dict, rows: List[dict], cfg: Config) -> None:
    st.markdown("**Signal breakdown** — this ticker vs the pool")
    recs = []
    for name in cfg.signal_weights:
        v = row.get(name)
        pool = np.array([r[name] for r in rows if r.get(name) is not None], dtype=float)
        pct = float((pool < v).mean()) if (v is not None and len(pool)) else None
        recs.append({
            "signal": name,
            "category": data.CATEGORY_LABELS[cfg.signal_categories[name]],
            "score": v,
            "pool pctile": pct,
            "weight": data._weight_of(name, cfg),
            "contribution": (v * data._weight_of(name, cfg)) if v is not None else None,
        })
    df = pd.DataFrame(recs)
    st.dataframe(
        df, hide_index=True, width="stretch",
        column_config={
            "score": st.column_config.ProgressColumn(min_value=0.0, max_value=10.0, format="%.2f"),
            "pool pctile": st.column_config.NumberColumn(format="%.0f%%", help="share of the pool below this"),
            "weight": st.column_config.NumberColumn(format="%.3f"),
            "contribution": st.column_config.NumberColumn(format="%.3f"),
        },
    )
    missing = [r["signal"] for r in recs if r["score"] is None]
    if missing:
        st.caption(
            f"**Not observed:** {', '.join(missing)} — these renormalize away rather than being "
            "imputed to 5.0. `coverage` is what is left: **{:.0%}**.".format(row.get("coverage", 0))
        )


def _monte_carlo(row: dict, snap: Snapshot, cfg: Config, ticker: str) -> None:
    st.markdown(f"**Monte Carlo** — {cfg.mc_horizon_days} trading days (~2y), "
                f"{cfg.mc_sims:,} bootstrap paths")
    prices = data.closes(snap, ticker)
    terminal = (simulate_terminal(prices.to_numpy(dtype=float), cfg.mc_horizon_days,
                                  cfg.mc_sims, cfg.mc_seed)
                if prices is not None else None)
    if terminal is None:
        st.caption("Not enough history to simulate.")
        return

    c = st.columns(4)
    c[0].metric(f"P(gain ≥ {cfg.mc_goal:.0%})", f"{row.get('p_goal_2y', 0):.1%}")
    c[1].metric(f"P(loss ≤ {cfg.mc_bust:.0%})", f"{row.get('p_bust_2y', 0):.1%}")
    c[2].metric("Median outcome", f"{np.median(terminal):+.1%}")
    c[3].metric("MC confidence", f"{row.get('mc_confidence', 0):.2f}")

    counts, edges = np.histogram(np.clip(terminal, -1.0, 3.0), bins=60)
    st.bar_chart(pd.DataFrame({"paths": counts},
                              index=[f"{e:+.0%}" for e in edges[:-1]]), height=220)
    st.caption(
        "Display and filter only — **never in the composite.** P(goal) is ρ +0.98 with sharpe "
        "and P(bust) ρ +0.94 with volatility: they are sharpe and volatility in a percentage "
        "costume, and weighting them would double-count the ladder. `mc_confidence` is low for a "
        "reason — P(goal) swings 53-68 points across ±1 SE of drift."
    )


def _tearsheet(snap: Snapshot, cfg: Config, ticker: str, run_ts: str) -> None:
    st.markdown("**quantstats tearsheet**")
    tearsheet.render_tearsheet(snap, cfg, ticker, run_ts, key_prefix="detail_")
