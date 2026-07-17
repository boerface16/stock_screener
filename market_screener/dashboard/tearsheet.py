"""
quantstats tearsheets — display only, ranking nothing.

**THE RULE: feed quantstats RETURNS, never PRICES.**

`qs.stats.max_drawdown` prepends a phantom baseline chosen by tier (`_get_baseline_value`:
first price > 1000 -> 1e5, > 10 -> 100.0, else 1.0) and that baseline joins the running peak.
So a price series is measured against a level the stock never traded at: KO's 5y drawdown comes
back -54.40% (= 45.60/100 - 1) when the truth is -17.3%. Measured on the real pool, prices-in is
wrong for 165/373 tickers (44%, max error 78.5%); returns-in is exact (0/373 wrong).

SPY and AAPL return correct answers on prices because they trade *above* 100 — which is exactly
why a spot-check would clear this. Do not spot-check it. Feed it returns.

`_to_returns` is the only entry point to quantstats here, and `verify_against_metrics` asserts
the report agrees with scoring/metrics.py — the repo's own hand-verified numpy implementation,
which stays the scoring path regardless (4x faster, matches to 0.00e+00).
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional, Tuple

import matplotlib
matplotlib.use("Agg")           # must precede the quantstats import — no display on a server

import pandas as pd
import quantstats as qs
import streamlit as st
import streamlit.components.v1 as components

from config import Config
from scoring.metrics import max_drawdown as np_max_drawdown
from scoring.metrics import sharpe as np_sharpe


def _to_returns(prices: pd.Series) -> pd.Series:
    """Prices -> simple returns. The ONLY thing that may reach quantstats. See module docstring."""
    return prices.pct_change().dropna()


def window_slice(prices: pd.Series, bars: int) -> Optional[pd.Series]:
    """The last `bars` trading days, or None if the history is too short to fill the window."""
    if prices is None or len(prices) < bars:
        return None
    return prices.iloc[-bars:]


def verify_against_metrics(prices: pd.Series) -> Tuple[float, float, float, float]:
    """(qs_sharpe, np_sharpe, qs_maxdd, np_maxdd) over the same window.

    Shown in the UI rather than hidden in a test: the tearsheet is a third-party rendering of
    numbers the screener computes itself, and the two agreeing is the only reason to trust it.
    """
    r = _to_returns(prices)
    return (
        float(qs.stats.sharpe(r)),
        float(np_sharpe(prices.to_numpy(dtype=float))),
        float(qs.stats.max_drawdown(r)),
        float(np_max_drawdown(prices.to_numpy(dtype=float))),
    )


@st.cache_data(show_spinner="Building tearsheet…", max_entries=32)
def build_html(run_ts: str, ticker: str, window: str,
               prices: pd.Series, bench: pd.Series) -> Optional[str]:
    """Full quantstats HTML report for `ticker` over `window`, benchmarked against SPY.

    Cached per (run_ts, ticker, window) — ~1.7s and ~730 KB each. `prices`/`bench` are args
    rather than looked up here so Streamlit hashes them into the key: a different snapshot with
    the same run_ts string cannot serve a stale report.
    """
    returns = _to_returns(prices)
    bench_returns = _to_returns(bench)
    if returns.empty or bench_returns.empty:
        return None

    returns.name = ticker
    bench_returns.name = "SPY"
    # quantstats aligns on the index; an unaligned benchmark silently drops rows.
    bench_returns = bench_returns.reindex(returns.index).dropna()
    returns = returns.reindex(bench_returns.index)

    path = os.path.join(tempfile.gettempdir(), f"qs_{run_ts}_{ticker}_{window}.html")
    try:
        qs.reports.html(
            returns,
            benchmark=bench_returns,
            output=path,
            title=f"{ticker} vs SPY — {window}",
            # Labels the returns column in the report tables with the ticker instead of the
            # default "Strategy" (quantstats reads kwargs["strategy_title"], reports.py:281).
            strategy_title=ticker,
            benchmark_title="SPY",
            # PNG figures, not the default SVG: quantstats inlines 14 matplotlib SVGs that share
            # element IDs (clip-paths, glyphs) with ~1300 <use href="#id"> refs. In one document
            # those refs resolve to the FIRST matching id, so every plot after the first renders
            # with the wrong clip-paths — garbled, cut-off output. Self-contained base64 PNGs have
            # no shared IDs and render correctly. (Report ~15% larger; display-only, so fine.)
            figfmt="png",
            download_filename=path,
        )
    except Exception as e:                      # a broken report must not take down the page
        return f"__ERROR__{type(e).__name__}: {e}"

    with open(path, encoding="utf-8") as f:
        html = f.read()
    os.remove(path)
    return html


def render_tearsheet(snap, cfg: Config, ticker: str, run_ts: str, key_prefix: str = "") -> None:
    """The window picker + verify-vs-metrics banner + embedded quantstats report for one ticker.

    Shared by the Ticker-detail tab and the click-a-symbol panel under Rankings, so both render
    identically from one implementation. `key_prefix` disambiguates the window radio when the same
    ticker is shown in two places at once (Streamlit widget keys are global).
    """
    from dashboard import data      # local import: data.py has no need to import tearsheet back

    windows = list(cfg.ladder_windows)
    default = windows.index(cfg.risk_window) if cfg.risk_window in windows else 0
    window = st.radio(
        "Window", windows, index=default, horizontal=True,
        key=f"{key_prefix}ts_window_{ticker}",
        help="These are config.ladder_windows — the same windows the grades come from, so the "
             "report agrees with the ladder. There is no 2y window; 2.5y is holding-period-matched.",
    )

    bars = cfg.ladder_windows[window]
    prices = data.closes(snap, ticker)
    bench = data.closes(snap, cfg.benchmark, "reference")
    if prices is None or bench is None:
        st.warning("No price history for this ticker or the benchmark.")
        return

    px = window_slice(prices, bars)
    bx = window_slice(bench, bars)
    if px is None:
        yrs = len(prices) / cfg.trading_days_per_year
        st.warning(f"{ticker} has only **{yrs:.1f}y** of history — not enough for the "
                   f"{window} window ({bars} bars). Pick a shorter window.")
        return

    qs_sharpe, np_sharpe_val, qs_dd, np_dd = verify_against_metrics(px)
    agree = abs(qs_sharpe - np_sharpe_val) < 1e-6 and abs(qs_dd - np_dd) < 1e-6
    c = st.columns(2)
    c[0].metric("Sharpe", f"{np_sharpe_val:+.4f}",
                help=f"quantstats: {qs_sharpe:+.4f} · scoring/metrics.py: {np_sharpe_val:+.4f}")
    c[1].metric("Max drawdown", f"{np_dd:+.2%}",
                help=f"quantstats: {qs_dd:+.4f} · scoring/metrics.py: {np_dd:+.4f}")
    if agree:
        st.success(
            "quantstats agrees with `scoring/metrics.py` to 1e-6 — **because it is fed returns.** "
            "Fed *prices* it would prepend a phantom baseline (100.0 for anything starting above "
            "$10) and measure the drawdown from a price this stock never traded at: wrong for "
            "44% of the pool, by up to 78 points."
        )
    else:
        st.error(
            f"**quantstats disagrees with `scoring/metrics.py`.** sharpe {qs_sharpe:+.6f} vs "
            f"{np_sharpe_val:+.6f}, maxdd {qs_dd:+.6f} vs {np_dd:+.6f}. The repo's numpy version "
            "is hand-verified — trust it, and treat the report below as suspect."
        )

    html = build_html(run_ts, ticker, window, px, bx)
    if html is None:
        st.warning("Not enough overlapping data with the benchmark to build a report.")
    elif html.startswith("__ERROR__"):
        st.error(f"Tearsheet failed: {html[9:]}")
    else:
        components.html(html, height=900, scrolling=True)
