"""
Dashboard entry point.  `streamlit run dashboard/app.py`.

The whole codebase assumes cwd is `market_screener/` (PROJECT_MAP Gotcha 2): imports are flat
(`from config import Config`) and paths are relative to it (`snapshot_dir = "data/raw"`,
`outputs_TA/`). Two things break if the launch cwd is elsewhere — which `streamlit run` makes
easy, since it does not require you to be in `market_screener/`:
  1. imports: streamlit puts the *script's* dir (`dashboard/`) on sys.path[0], not the cwd.
  2. snapshot lookup: a relative `data/raw` resolves against the wrong directory and finds
     nothing — the "No snapshots under data/raw" error.
So the entry point establishes the invariant itself: put `market_screener/` on the path AND make
it the cwd, so the dashboard resolves paths identically to `python screener.py` regardless of
where it was launched.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # market_screener/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)     # so relative paths (data/raw, outputs_TA) resolve like the screener's do

import time

import streamlit as st

from config import Config
from dashboard import data, runner
from dashboard.views import diagnostics, table, ticker, tracking, weights

st.set_page_config(page_title="Screener", page_icon="📈", layout="wide")

# How often the progress panel polls the ingest log while a run is in flight.
_POLL_SECONDS = 2


def main() -> None:
    cfg = Config()
    st.sidebar.title("📈 Screener")

    # A finished ingest, closed out here so the new snapshot is selectable this same rerun.
    finished = runner.finalize()
    if finished is not None:
        runs_now = data.list_runs(cfg)
        if finished["returncode"] == 0 and runs_now:
            st.session_state["run_select"] = runs_now[0]          # snap the picker to the new run
            st.session_state["ingest_toast"] = (
                "success",
                f"Run complete in {finished['seconds']:.0f}s — snapshot {runs_now[0]} loaded and a "
                "dated CSV written for the Tracking tab.",
            )
        else:
            st.session_state["ingest_toast"] = (
                "error",
                f"Run exited with code {finished['returncode']} and wrote no usable snapshot. "
                "See the log below.",
            )

    _ingest_controls()

    # While a run is in flight, the whole main area is the progress panel — no point scoring and
    # rendering four tabs every two seconds. This returns after scheduling the next poll.
    if runner.is_running():
        _progress_panel()
        return

    runs = data.list_runs(cfg)
    if not runs:
        st.info(
            "No snapshots yet. Click **Run screener for today** in the sidebar to fetch today's "
            "market data — or run `python screener.py` from `market_screener/`. The dashboard "
            "reads snapshots, not the CSV."
        )
        _show_last_log()
        st.stop()

    # Keep the picker on a valid run; default to newest. A keyed selectbox lets finalize() above
    # move the selection programmatically.
    if st.session_state.get("run_select") not in runs:
        st.session_state["run_select"] = runs[0]
    run_ts = st.sidebar.selectbox(
        "Snapshot run", runs, key="run_select",
        help="Newest first. Each is a full ingest the scorer replays.",
    )

    _show_toast()

    # Score once per (snapshot, config): the fingerprint is the cache key, so editing config.py
    # invalidates it. This is the ~1-2 min cold path; every tab below reads its result.
    fingerprint = data.cfg_fingerprint(cfg)
    scored = data.get_scored(run_ts, fingerprint)
    snap = data.get_snapshot(run_ts)
    kept, dropped = data.split_filters(scored, cfg)
    full_pool = kept + dropped   # ranks on the keepers, dropped rows still selectable in detail

    st.sidebar.metric("Scored", len(scored))
    st.sidebar.metric("Passed filters", len(kept))
    st.sidebar.metric("Dropped", len(dropped))
    st.sidebar.caption(f"Config `{fingerprint}` · weights "
                       + "/".join(f"{v:.2f}" for v in cfg.weights.values()))

    tab_rank, tab_ticker, tab_track, tab_diag, tab_weights = st.tabs(
        ["Rankings", "Ticker detail", "Tracking", "Diagnostics", "Weight tuning"]
    )
    with tab_rank:
        table.render(kept, dropped, snap, cfg, run_ts)
    with tab_ticker:
        ticker.render(full_pool, snap, cfg, run_ts)
    with tab_track:
        tracking.render(cfg, fingerprint)
    with tab_diag:
        diagnostics.render(scored, cfg)
    with tab_weights:
        weights.render(scored, cfg)


def _ingest_controls() -> None:
    """The 'run it for today' button, or a live status line while it runs."""
    st.sidebar.divider()
    st.sidebar.subheader("Data")
    if runner.is_running():
        st.sidebar.warning(f"Ingesting today's data… {runner.elapsed():.0f}s elapsed")
        return
    if st.sidebar.button("↻ Run screener for today", type="primary"):
        runner.start()
        st.rerun()
    st.sidebar.caption(
        "Runs the full screener (~4–5 min: fetch today's data, snapshot it, score, rank). Writes a "
        "new snapshot the dashboard reads **and** a dated CSV under `outputs_TA/` — the CSV is what "
        "the Tracking tab picks up as a new cohort."
    )


def _progress_panel() -> None:
    """Full-page ingest status; polls the log and reschedules itself until the child exits."""
    st.subheader("Running the screener")
    st.caption(
        "Running the full screener as a subprocess (`screener.py`): ingest → snapshot → score → "
        "write the dated CSV. You can leave this tab — it keeps running."
    )
    st.info(f"Elapsed: {runner.elapsed():.0f}s")
    st.code(runner.read_log(tail=40) or "starting…", language="log")
    if st.button("Stop ingest"):
        runner.stop()
        st.rerun()
    time.sleep(_POLL_SECONDS)
    st.rerun()


def _show_toast() -> None:
    toast = st.session_state.pop("ingest_toast", None)
    if not toast:
        return
    kind, msg = toast
    (st.success if kind == "success" else st.error)(msg)


def _show_last_log() -> None:
    log = runner.read_log(tail=40)
    if log:
        with st.expander("Last ingest log"):
            st.code(log, language="log")


if __name__ == "__main__" or True:   # streamlit imports the module rather than running __main__
    main()
