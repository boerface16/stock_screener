#!/usr/bin/env python3
import argparse
import csv
import os
import sys
from datetime import datetime
from typing import List

# Ensure stdout handles Unicode on Windows (crawl4ai outputs non-ASCII chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import Config
from ingest import ingest
from snapshot import latest_run_ts, load_snapshot, write_snapshot
from scoring.reason import build_reason
from scoring.scorer import score_all


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Market Screener — free-data stock screener")
    parser.add_argument("--n", type=int, default=None, help="Number of tickers in final output (default: 50)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Deprecated no-op: ranking is always deterministic now, and the "
                             "reason column is a template built from the real drivers")
    parser.add_argument("--output", type=str, default="", help="Custom output CSV filename")
    parser.add_argument("--replay", type=str, nargs="?", const="latest", default=None,
                        metavar="RUN_TS",
                        help="Re-score a saved snapshot with no network. Omit the value for the newest.")
    parser.add_argument("--ingest-only", action="store_true", help="Fetch and snapshot, then stop")
    return parser.parse_args()


def signal_fieldnames(cfg: Config) -> List[str]:
    """Ladder columns are config-driven, so the CSV header follows cfg.ladder_windows."""
    return [
        "rank", "ticker", "composite_score", "coverage",
        # ranking signals, in category order
        *cfg.signal_weights.keys(),
        # display only — weight 0. gold_gpa is the 0-4 report card behind gold_score.
        "gold_gpa", "gold_worst", "grades", "windows_available", "history_years",
        *[f"xs_{w}" for w in cfg.ladder_windows],
        "divergence", "meme_flag", "news_buzz", "social_buzz", "rel_volume",
        "max_drawdown_raw", "volatility_raw",
        "p_goal_2y", "p_bust_2y", "mc_confidence",
        "sector", "price_usd", "llm_reason", "run_timestamp",
    ]


def write_csv(rows: List[dict], filepath: str, fieldnames: List[str]) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def print_table(rows: List[dict]) -> None:
    def _n(v, w=5, p=1):
        return f"{v:>{w}.{p}f}" if isinstance(v, (int, float)) else f"{'-':>{w}}"

    header = (
        f"{'Rank':>4}  {'Ticker':<6}  {'Score':>6}  {'Cov':>5}  {'Val':>5}  {'Qual':>5}  "
        f"{'Grow':>5}  {'GPA':>5}  {'Grades':<17}  {'Yrs':>5}  {'Cap':>5}  "
        f"{'Price':>9}  Reason"
    )
    print("\n" + header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['rank']:>4}  {row['ticker']:<6}  {_n(row['composite_score'], 6, 2)}  "
            f"{_n(row.get('coverage'), 5, 2)}  {_n(row.get('value'))}  {_n(row.get('quality'))}  "
            f"{_n(row.get('growth'))}  {_n(row.get('gold_gpa'))}  "
            f"{str(row.get('grades') or ''):<17}  {_n(row.get('history_years'))}  "
            f"{_n(row.get('capitol_hill'))}  "
            f"${_n(row.get('price_usd'), 8, 2)}  {row.get('llm_reason', '')}"
        )
    print()


def main() -> None:
    args = parse_args()
    cfg = Config()

    if args.n is not None:
        cfg.n_results = args.n

    # Phase 1: Ingest — the only network phase. Everything scoring reads lands in a snapshot.
    if args.replay:
        run_ts = latest_run_ts(cfg) if args.replay == "latest" else args.replay
        if run_ts is None:
            print(f"[ERROR] No snapshots found in {cfg.snapshot_dir}. Run without --replay first.")
            sys.exit(1)
        print(f"[INFO] Replaying snapshot {run_ts} (no network)...")
        snap = load_snapshot(cfg, run_ts)
    else:
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = ingest(cfg, run_ts)
        if not snap.pool:
            print("[ERROR] Universe seeding returned empty pool. Exiting.")
            sys.exit(1)
        print(f"[INFO] Snapshot written to {write_snapshot(snap, cfg)}")
        if args.ingest_only:
            print(f"[INFO] --ingest-only set. Re-score it with: python screener.py --replay {run_ts}")
            return

    # Timestamps follow the snapshot, not the clock: a replay describes when the data was
    # captured, and it keeps two replays of one snapshot byte-identical.
    run_date = datetime.strptime(run_ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d")
    output_filename = args.output or f"screener_{run_ts}.csv"
    output_path = os.path.join(cfg.output_dir, run_date, output_filename)
    os.makedirs(os.path.join(cfg.output_dir, run_date), exist_ok=True)

    # Phase 2: Scoring — pure function of the snapshot
    print(f"\n[INFO] Scoring {len(snap.pool)} tickers...")
    scored = score_all(snap, cfg)
    print(f"[INFO] Scoring complete. {len(scored)} tickers passed filters.")

    if not scored:
        print("[ERROR] No tickers survived scoring. Exiting.")
        sys.exit(1)

    # Phase 3: rank + explain. The LLM is out of the ranking path entirely — it saw six numbers
    # per ticker and was asked to judge news catalysts and market caps it could not see, so it
    # narrated the dead `news` constant back as evidence. The reason is now a template built
    # from the drivers that actually moved the rank.
    ranked = [
        {**c, "rank": i + 1, "llm_reason": build_reason(c, cfg), "run_timestamp": run_ts}
        for i, c in enumerate(scored[:cfg.n_results])
    ]

    # Phase 4: Output
    print_table(ranked)
    write_csv(ranked, output_path, signal_fieldnames(cfg))
    print(f"[INFO] Done. {len(ranked)} tickers written to {output_path}")


if __name__ == "__main__":
    main()
