"""Rankings — the whole scored pool, filterable. The "what did it pick" view."""
from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from config import Config
from dashboard import data, tearsheet
from snapshot import Snapshot

# Columns worth seeing first. Everything else stays available behind "all columns".
_HEADLINE = [
    "rank", "ticker", "composite_score", "coverage", "sector", "price_usd",
    "value", "quality", "growth", "gold_score", "max_drawdown", "volatility",
    "news_sentiment", "social_sentiment", "capitol_hill",
    "gold_gpa", "grades", "windows_available", "history_years", "meme_flag", "reason",
]


def render(kept: List[dict], dropped: List[dict], snap: Snapshot, cfg: Config, run_ts: str) -> None:
    st.subheader("Rankings")
    st.caption(
        f"**{len(kept)}** tickers passed the filters out of **{len(kept) + len(dropped)}** scored. "
        "This is the full pool — the CSV only ever holds the top `--n`. "
        "**Click a row** to open its quantstats tearsheet below."
    )

    df = data.to_frame(kept)
    if df.empty:
        st.warning("No tickers passed the filters.")
        return

    df = _add_reason(df, cfg)

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        sectors = sorted(s for s in df["sector"].dropna().unique() if s)
        pick = st.multiselect("Sector", sectors, default=[])
    with c2:
        search = st.text_input("Ticker search", "", placeholder="e.g. EFC, JPM")
    with c3:
        meme_only = st.checkbox("Meme flag only", value=False)

    c4, c5 = st.columns(2)
    with c4:
        lo, hi = float(df["composite_score"].min()), float(df["composite_score"].max())
        # A degenerate range would make st.slider raise; it also means filtering is pointless.
        score_range = st.slider("Composite score", lo, hi, (lo, hi)) if hi > lo else (lo, hi)
    with c5:
        cov_lo = float(df["coverage"].min())
        coverage_min = (st.slider("Minimum coverage", cov_lo, 1.0, cov_lo)
                        if cov_lo < 1.0 else cov_lo)

    view = df
    if pick:
        view = view[view["sector"].isin(pick)]
    if search.strip():
        wanted = {t.strip().upper() for t in search.replace(",", " ").split()}
        view = view[view["ticker"].isin(wanted)]
    if meme_only:
        view = view[view["meme_flag"] == True]  # noqa: E712 — pandas mask, not a bool test
    view = view[(view["composite_score"] >= score_range[0])
                & (view["composite_score"] <= score_range[1])
                & (view["coverage"] >= coverage_min)]

    show_all = st.checkbox("Show all columns", value=False)
    cols = list(view.columns) if show_all else [c for c in _HEADLINE if c in view.columns]

    event = st.dataframe(
        view[cols],
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="rank_table",
        column_config={
            "composite_score": st.column_config.ProgressColumn(
                "composite", min_value=0.0, max_value=10.0, format="%.2f"),
            "coverage": st.column_config.NumberColumn("coverage", format="%.2f"),
            "price_usd": st.column_config.NumberColumn("price", format="$%.2f"),
            "gold_gpa": st.column_config.NumberColumn("GPA", format="%.2f", help="0-4 report card"),
            "reason": st.column_config.TextColumn("reason", width="large"),
        },
    )
    st.caption(f"{len(view)} of {len(df)} rows shown.")

    csv = view[cols].to_csv(index=False).encode("utf-8")
    st.download_button("Download this view as CSV", csv,
                       file_name=f"screener_view_{len(view)}rows.csv", mime="text/csv")

    _selected_tearsheet(event, view, snap, cfg, run_ts)

    with st.expander(f"Dropped by filters ({len(dropped)}) — and why"):
        if not dropped:
            st.write("Nothing was dropped.")
        else:
            dd = data.to_frame(dropped)
            st.dataframe(
                dd[["ticker", "composite_score", "coverage", "sector", "dropped_for"]],
                width="stretch", hide_index=True,
                column_config={"dropped_for": st.column_config.TextColumn(
                    "dropped for", width="large")},
            )


def _selected_tearsheet(event, view: pd.DataFrame, snap: Snapshot,
                        cfg: Config, run_ts: str) -> None:
    """Render the clicked row's tearsheet under the table. `event.selection.rows` are positional
    indices into the displayed frame, which shares `view`'s row order — so `view.iloc` maps back."""
    rows = getattr(getattr(event, "selection", None), "rows", None) or (
        event.get("selection", {}).get("rows", []) if isinstance(event, dict) else [])
    if not rows:
        st.info("Click a row above to see its quantstats tearsheet here.")
        return
    picked = str(view.iloc[rows[0]]["ticker"])
    st.divider()
    st.markdown(f"### {picked} — quantstats tearsheet")
    tearsheet.render_tearsheet(snap, cfg, picked, run_ts, key_prefix="rank_")


def _add_reason(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """`reason` is built by screener.py at CSV time, not by the scorer, so it is absent here."""
    from scoring.reason import build_reason
    df = df.copy()
    df["reason"] = [build_reason(r, cfg) for r in df.to_dict("records")]
    return df
