"""
Run the screener from inside the dashboard.

Launches `python screener.py` (a **full run**: ingest + score + write CSV) as a **subprocess** —
the actual CLI, not a reimplementation, so the dashboard can never drift from what the screener
writes. It is a full run, not `--ingest-only`, because the CSV it produces under `outputs_TA/` is
what the Tracking tab reads as a cohort; ingest-only would snapshot but write no CSV. Three reasons
it is a subprocess and not an in-process call:
  1. Ingest is the only network phase and runs for minutes; a subprocess keeps it off Streamlit's
     script thread, which reruns top-to-bottom on every interaction.
  2. Ingest drives crawl4ai (asyncio) and a thread pool — neither mixes cleanly with Streamlit's
     ScriptRunner thread.
  3. It streams a live log.
stdout is redirected to a **file**, not a PIPE: a verbose child whose pipe buffer fills while
Streamlit sits between reruns would deadlock. A file never backpressures.

State lives in st.session_state under one key, so a job survives the reruns that poll it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from typing import Optional

import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # market_screener/
_LOG_DIR = os.path.join(tempfile.gettempdir(), "screener_ingest")
_KEY = "ingest_job"


def is_running() -> bool:
    job = st.session_state.get(_KEY)
    return bool(job and job["proc"].poll() is None)


def start() -> None:
    """Spawn a full `screener.py` run (ingest + score + CSV). No-op if one is already running."""
    if is_running():
        return
    os.makedirs(_LOG_DIR, exist_ok=True)
    started = datetime.now()
    log_path = os.path.join(_LOG_DIR, started.strftime("%Y%m%d_%H%M%S") + ".log")
    logf = open(log_path, "w", encoding="utf-8", errors="replace")
    # -u: unbuffered, so the log file fills line-by-line and the UI can tail progress live.
    # cwd=_ROOT so the child writes to the same data/raw + outputs_TA the dashboard reads (app.py).
    # Full run (no --ingest-only): it must write the CSV the Tracking tab reads as a cohort.
    proc = subprocess.Popen(
        [sys.executable, "-u", "screener.py"],
        cwd=_ROOT, stdout=logf, stderr=subprocess.STDOUT, text=True,
    )
    st.session_state[_KEY] = {"proc": proc, "logf": logf, "log_path": log_path,
                              "started": started.timestamp()}


def stop() -> None:
    job = st.session_state.get(_KEY)
    if not job:
        return
    if job["proc"].poll() is None:
        job["proc"].terminate()
        try:
            job["proc"].wait(timeout=10)
        except subprocess.TimeoutExpired:
            job["proc"].kill()
    _close(job)
    st.session_state.pop(_KEY, None)


def elapsed() -> float:
    job = st.session_state.get(_KEY)
    return time.time() - job["started"] if job else 0.0


def read_log(tail: int = 40) -> str:
    """Last `tail` lines of the running (or just-finished) job's log."""
    job = st.session_state.get(_KEY)
    path = job["log_path"] if job else (st.session_state.get("ingest_result") or {}).get("log_path")
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-tail:])


def finalize() -> Optional[dict]:
    """If a running job has exited, close it out and return its result; else None.

    Call once per rerun before the run picker renders, so the newest snapshot is selectable the
    instant ingest exits. Returns {returncode, seconds, log_path} on the transition, once.
    """
    job = st.session_state.get(_KEY)
    if not job:
        return None
    rc = job["proc"].poll()
    if rc is None:
        return None
    _close(job)
    result = {"returncode": rc, "seconds": time.time() - job["started"],
              "log_path": job["log_path"]}
    st.session_state["ingest_result"] = result
    st.session_state.pop(_KEY, None)
    return result


def _close(job) -> None:
    try:
        job["logf"].close()
    except Exception:
        pass
