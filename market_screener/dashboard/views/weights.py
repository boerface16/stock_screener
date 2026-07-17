"""
Weight tuning — drag the category weights, watch the ranking move.

The 0.45/0.35/0.10/0.10 prior is an explicit guess, not a fitted result: `tasks/todo.md` Phase
3.4 fits it from IC once forward returns exist, and at a 2-year horizon that is years away. This
view makes the guess visible — if the top 20 barely moves when you halve a category, that
category was not doing much work.

It re-derives the composite from already-scored signals via the production `scorer.composite`.
No re-scoring, no Monte Carlo, no second copy of the renormalization.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from config import Config
from dashboard import data


def render(rows: List[dict], cfg: Config) -> None:
    st.subheader("Weight tuning")
    st.warning(
        "**These weights are a guess.** 0.45/0.35/0.10/0.10 is an explicit prior, not a fitted "
        "result — nothing in this screener is yet known to predict returns. Phase 3.4 fits them "
        "from information coefficient once forward data exists. Until then, this view is for "
        "seeing how much each category is actually moving the ranking.",
        icon="⚠️",
    )

    base = cfg.weights
    cols = st.columns(len(base))
    picked: Dict[str, float] = {}
    for col, (cat, default) in zip(cols, base.items()):
        with col:
            picked[cat] = st.slider(
                data.CATEGORY_LABELS[cat], 0.0, 1.0, float(default), 0.05,
                key=f"w_{cat}",
            )

    total = sum(picked.values())
    if total <= 0:
        st.error("All weights are zero — nothing to rank on.")
        return

    tuned_cfg = data.with_weights(cfg, picked)
    if abs(total - 1.0) > 1e-9:
        st.caption(
            f"Weights sum to **{total:.2f}**, renormalized to 1.0 → "
            + ", ".join(f"{data.CATEGORY_LABELS[c]} **{w:.3f}**"
                        for c, w in tuned_cfg.weights.items())
            + ". Renormalized because `coverage` is the fraction of *total* weight observed and "
              "is gated at "
            + f"{cfg.min_coverage:.0%} — unnormalized weights would inflate it and admit tickers "
              "the real screener drops."
        )

    if st.button("Reset to the shipped prior"):
        for cat in base:
            st.session_state[f"w_{cat}"] = float(base[cat])
        st.rerun()

    base_kept, _ = data.split_filters(data.rescore(rows, cfg), cfg)
    tuned_kept, tuned_dropped = data.split_filters(data.rescore(rows, tuned_cfg), tuned_cfg)

    base_rank = {r["ticker"]: r["rank"] for r in base_kept}
    frame = pd.DataFrame([
        {
            "rank": r["rank"],
            "ticker": r["ticker"],
            "composite": r["composite_score"],
            "Δ rank": (base_rank[r["ticker"]] - r["rank"]) if r["ticker"] in base_rank else None,
            "was": base_rank.get(r["ticker"]),
            "sector": r.get("sector"),
            "coverage": r.get("coverage"),
        }
        for r in tuned_kept[:50]
    ])

    c = st.columns(3)
    c[0].metric("Passing filters", len(tuned_kept), delta=len(tuned_kept) - len(base_kept))
    moved = int((frame["Δ rank"].fillna(0) != 0).sum()) if len(frame) else 0
    c[1].metric("Top 50 that moved", moved)
    top10_base = {r["ticker"] for r in base_kept[:10]}
    top10_tuned = {r["ticker"] for r in tuned_kept[:10]}
    c[2].metric("Top 10 unchanged", f"{len(top10_base & top10_tuned)}/10")

    st.dataframe(
        frame, hide_index=True, width="stretch",
        column_config={
            "composite": st.column_config.ProgressColumn(min_value=0.0, max_value=10.0, format="%.2f"),
            "Δ rank": st.column_config.NumberColumn(
                format="%+d", help="positive = moved up vs the shipped prior"),
            "coverage": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.caption(f"Top 50 under the tuned weights. {len(tuned_dropped)} tickers fail the filters.")

    entered = [t for t in top10_tuned - top10_base]
    left = [t for t in top10_base - top10_tuned]
    if entered or left:
        st.info(f"**Top 10 in:** {', '.join(sorted(entered)) or '—'}  ·  "
                f"**out:** {', '.join(sorted(left)) or '—'}")
