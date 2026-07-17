"""
Signal diagnostics — is each signal actually alive?

This view exists because of a specific, repeated failure: `news` sat constant at 10.0 and
`social` at 0.00 across all 381 rows, and both looked like working signals in the output —
plausible numbers in a plausible range. Every source swallows its own exceptions, so a dead
source is indistinguishable from a quiet market. tasks/lessons.md: "Before trusting any signal,
check its spread across a real run: sd, distinct value count, and fraction pinned at min/max."

That check was ad-hoc and got run once, by hand, months late. Here it is standing.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
import streamlit as st

from config import Config
from dashboard import data


def render(rows: List[dict], cfg: Config) -> None:
    st.subheader("Signal diagnostics")
    st.caption(
        f"Spread of every ranking signal across the **{len(rows)}** scored tickers "
        "(unfiltered — this is signal health, not a screen)."
    )

    stats = data.signal_stats(rows, cfg)
    bad = stats[stats["health"] != "ok"]
    if len(bad):
        for _, r in bad.iterrows():
            st.warning(f"**{r['signal']}** — {r['health']}  ·  carries weight **{r['weight']:.3f}**")
    else:
        st.success("Every signal has real spread. No dead, saturated, or inert signals.")

    st.dataframe(
        stats, hide_index=True, width="stretch",
        column_config={
            "weight": st.column_config.NumberColumn(format="%.3f"),
            "sd": st.column_config.NumberColumn(format="%.3f", help="0 means the signal ranks nothing"),
            "at_min": st.column_config.NumberColumn("pinned low", format="%.0f%%"),
            "at_max": st.column_config.NumberColumn("pinned high", format="%.0f%%"),
            "missing": st.column_config.NumberColumn(help="scored None — renormalizes away"),
            "health": st.column_config.TextColumn(width="large"),
        },
    )

    st.markdown("**Distributions**")
    signals = list(cfg.signal_weights)
    pick = st.multiselect("Signals", signals, default=signals[:3])
    for name in pick:
        vals = [r[name] for r in rows if r.get(name) is not None]
        if not vals:
            st.caption(f"**{name}** — never observed.")
            continue
        counts, edges = np.histogram(vals, bins=40, range=(0.0, 10.0))
        st.caption(f"**{name}** — n={len(vals)}, sd={np.std(vals):.3f}, "
                   f"{len(np.unique(np.round(vals, 4)))} distinct")
        st.bar_chart(pd.DataFrame({name: counts},
                                  index=[f"{e:.1f}" for e in edges[:-1]]), height=180)

    st.divider()
    _coverage(rows, cfg)


def _coverage(rows: List[dict], cfg: Config) -> None:
    st.markdown("**Coverage** — the fraction of ranking weight actually observed per ticker")
    cov = [r.get("coverage", 0.0) for r in rows]
    c = st.columns(3)
    c[0].metric("Median coverage", f"{np.median(cov):.0%}")
    c[1].metric(f"Below the {cfg.min_coverage:.0%} gate",
                f"{sum(1 for v in cov if v < cfg.min_coverage)}")
    c[2].metric("Fully covered", f"{sum(1 for v in cov if v >= 0.999)}")
    counts, edges = np.histogram(cov, bins=20, range=(0.0, 1.0))
    st.bar_chart(pd.DataFrame({"tickers": counts},
                              index=[f"{e:.0%}" for e in edges[:-1]]), height=200)
    st.caption(
        "Missing signals renormalize away and are **never imputed to 5.0** — 5.0 is reserved for "
        "\"measured, and average\". `capitol_hill` was once 5.0 for 8 of 20 rows, which was "
        "indistinguishable from a genuinely average ticker."
    )
