"""
Shared reader for screener CSVs, used by both second-pass pipes.

This was two byte-identical copies (SIGNAL_COLS + find_latest_screener_csv + load_tickers) in
TradingAgents_pipe.py and HedgeFund_pipe.py. Duplicated fetchers drift: the same class of bug
left one Wikipedia fetcher with a User-Agent and its twin returning 403 (tasks/lessons.md).

The schema guard exists because both pipes write with extrasaction="ignore". Feeding them a
CSV whose columns have changed produced blank cells rather than an error — a silent wrong
answer, which is the failure mode this whole overhaul is aimed at.
"""
import csv
import glob
import sys
from pathlib import Path
from typing import List

SCREENER_OUTPUT_DIR = Path(r"A:\Stonks\Screener_Tool\output")

# The ranking signals a screener CSV must carry — mirrors config.signal_weights. Update in
# lockstep with screener.py's fieldnames; a mismatch here is meant to stop a run, not degrade it.
# Changed 2026-07-16 with the signal-layer overhaul: the old set (momentum/volume/news/social/
# fundamentals/capitol_hill) is gone. Attention signals left the composite entirely, and
# fundamentals split into value/quality/growth. Pre-overhaul CSVs no longer load, by design —
# they were scored by a pipeline with a dead news signal and a random pool cap.
SIGNAL_COLS = [
    "value", "quality", "growth",
    "gold_score", "max_drawdown", "volatility",
    "news_sentiment", "social_sentiment",
    "capitol_hill",
]
REQUIRED_COLS = ["rank", "ticker", "composite_score", "coverage", "price_usd", *SIGNAL_COLS]


def find_latest_screener_csv() -> Path:
    matches = sorted(glob.glob(str(SCREENER_OUTPUT_DIR / "screener_*.csv")))
    if not matches:
        sys.exit(f"No screener CSV found in {SCREENER_OUTPUT_DIR}. Run screener.py first.")
    return Path(matches[-1])


def validate_schema(header: List[str], csv_path: Path) -> None:
    missing = [c for c in REQUIRED_COLS if c not in (header or [])]
    if missing:
        sys.exit(
            f"Schema mismatch in {csv_path}\n"
            f"  missing columns: {missing}\n"
            f"  found: {header}\n"
            f"This CSV was written by a different version of the screener. Re-run the screener "
            f"rather than scoring it — the pipes write with extrasaction='ignore', so continuing "
            f"would emit blank cells instead of failing."
        )


def load_tickers(csv_path: Path, n: int) -> List[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        validate_schema(reader.fieldnames, csv_path)
        rows = list(reader)
    rows.sort(key=lambda r: int(r["rank"]))
    return rows[:n]
