"""
Second-pass pipeline: feed market_screener top-N tickers through TradingAgents (Ollama)
and output a filtered buy list.

Usage:
    python pipeline.py [--n 40] [--model gemma4:latest] [--date 2026-05-12]
                       [--input path/to/screener.csv] [--output buys.csv]
                       [--analysts market,social,news,fundamentals]
                       [--debate-rounds 1] [--risk-rounds 1]
"""

import argparse
import csv
import time
import traceback
from datetime import date
from pathlib import Path

from screener_csv import SIGNAL_COLS, find_latest_screener_csv, load_tickers

TRADING_AGENTS_OUTPUT_DIR = Path(__file__).parent / "outputs_trading_agents"


def build_config(provider: str, model: str, debate_rounds: int, risk_rounds: int, recur_limit: int):
    from tradingagents.default_config import DEFAULT_CONFIG

    results_dir = Path(__file__).parent / "market_screener" / "output" / "ta_results"
    config = dict(DEFAULT_CONFIG)
    config.update({
        "llm_provider": provider,
        "deep_think_llm": model,
        "quick_think_llm": model,
        "max_debate_rounds": debate_rounds,
        "max_risk_discuss_rounds": risk_rounds,
        "max_recur_limit": recur_limit,
        "results_dir": str(results_dir),
    })
    return config


def build_graph(config, analysts: list[str]):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    return TradingAgentsGraph(
        selected_analysts=analysts,
        config=config,
        debug=False,
    )


RESULT_FIELDNAMES = ["date", "rank", "ticker", "price_usd", "ta_signal", "composite_score", "elapsed_s", "ta_reasoning"]


def write_results(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults written to {output_path}")


def write_buys(buys: list[dict], output_path: Path) -> None:
    if not buys:
        print("\nNo BUY signals found in this batch.")
        return

    fieldnames = [
        "rank", "ticker", "composite_score",
        *SIGNAL_COLS,
        "price_usd", "screener_reason", "ta_signal", "ta_reasoning",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(buys)
    print(f"Buy list written to {output_path}")


def write_reasoning(
    results: list[dict],
    output_path: Path,
    run_date: str,
    provider: str,
    model: str,
    timestamp: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# TradingAgents Analysis — {run_date}",
        f"Model: {provider}/{model}  |  Run: {timestamp}",
        "",
    ]
    for row in results:
        lines.append(f"## {row['ticker']}")
        lines.append(f"**Signal:** {row.get('ta_signal', 'N/A')}")
        lines.append(f"**Elapsed:** {row.get('elapsed_s', '')}s")
        lines.append(f"**Screener Score:** {row.get('composite_score', '')}")
        lines.append(f"**Price:** ${row.get('price_usd', 'N/A')}")
        lines.append("")
        lines.append("**Reasoning:**")
        lines.append(row.get("ta_reasoning_full", row.get("ta_reasoning", "")))
        lines.append("")
        lines.append("---")
        lines.append("")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Reasoning written to {output_path}")


def print_table(results: list[dict]) -> None:
    if not results:
        return
    header = f"{'Rank':>4}  {'Ticker':<6}  {'Price':>8}  {'Score':>10}  {'Signal':<6}  Reasoning"
    print("\n" + "=" * 95)
    print(header)
    print("-" * 95)
    for row in results:
        reasoning = row.get("ta_reasoning", "")[:55]
        price = row.get("price_usd", "")
        try:
            price_fmt = f"${float(price):>7.2f}"
        except (ValueError, TypeError):
            price_fmt = f"{'N/A':>8}"
        print(
            f"{row['rank']:>4}  {row['ticker']:<6}  {price_fmt}  "
            f"{float(row['composite_score']):>10.4f}  "
            f"{row.get('ta_signal', 'ERROR'):<6}  {reasoning}"
        )
    print("=" * 95)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TradingAgents second-pass on screener output")
    parser.add_argument("--n", type=int, default=40, help="Number of top tickers to analyze (default 40)")
    parser.add_argument("--model", default="gemma4:latest", help="Ollama model name (default gemma4:latest)")
    parser.add_argument("--date", default=str(date.today()), help="Trade date YYYY-MM-DD (default today)")
    parser.add_argument("--input", default=None, help="Path to screener CSV (default: latest in market_screener/output/)")
    parser.add_argument("--analysts", default="market,social,news,fundamentals",
                        help="Comma-separated analyst types (default: market,social,news,fundamentals)")
    parser.add_argument("--debate-rounds", type=int, default=1, help="Bull/Bear debate rounds (default 1)")
    parser.add_argument("--risk-rounds", type=int, default=1, help="Risk discussion rounds (default 1)")
    parser.add_argument("--provider", default="ollama", help="LLM provider (default ollama)")
    parser.add_argument("--recur-limit", type=int, default=150, help="LangGraph recursion limit (default 150)")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else find_latest_screener_csv()
    print(f"Loading screener results from: {input_path}")

    tickers = load_tickers(input_path, args.n)
    print(f"Analyzing top {len(tickers)} tickers: {[r['ticker'] for r in tickers]}")
    print(f"Trade date: {args.date}  |  Model: {args.model}  |  Provider: {args.provider}")

    analysts = [a.strip() for a in args.analysts.split(",")]

    print("\nInitializing TradingAgentsGraph...")
    config = build_config(args.provider, args.model, args.debate_rounds, args.risk_rounds, args.recur_limit)
    graph = build_graph(config, analysts)
    print("Graph ready.\n")

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = TRADING_AGENTS_OUTPUT_DIR / args.date
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ta_results_{timestamp}.csv"
    reasoning_path = output_dir / f"ta_reasoning_{timestamp}.md"

    all_results = []
    buys = []
    total = len(tickers)
    batch_start = time.time()

    for i, row in enumerate(tickers, start=1):
        ticker = row["ticker"]
        print(f"[{i}/{total}] Analyzing {ticker}...", end=" ", flush=True)
        t0 = time.time()
        try:
            final_state, signal = graph.propagate(ticker, args.date)
            elapsed = time.time() - t0
            signal_clean = signal.strip().upper()
            reasoning = final_state.get("final_trade_decision", "") or ""
            print(f"{signal_clean}  ({elapsed:.1f}s)")
            result = {
                **row,
                "date": args.date,
                "screener_reason": row.get("llm_reason", ""),
                "ta_signal": signal_clean,
                "ta_reasoning": reasoning[:500],
                "ta_reasoning_full": reasoning,
                "elapsed_s": round(elapsed, 1),
            }
            all_results.append(result)
            if signal_clean == "BUY":
                buys.append(result)
        except Exception:
            elapsed = time.time() - t0
            print(f"ERROR  ({elapsed:.1f}s)")
            traceback.print_exc()
            all_results.append({**row, "date": args.date, "ta_signal": "ERROR", "ta_reasoning": "", "ta_reasoning_full": "", "elapsed_s": round(elapsed, 1)})
            continue

    batch_elapsed = time.time() - batch_start
    mins, secs = divmod(int(batch_elapsed), 60)
    print(f"\nDone. {len(buys)} BUY signal(s) out of {total} analyzed.  Total time: {mins}m {secs}s")
    print_table(all_results)
    write_results(all_results, output_path)
    write_reasoning(all_results, reasoning_path, args.date, args.provider, args.model, timestamp)
    if buys:
        buys_path = output_dir / f"ta_buys_{timestamp}.csv"
        write_buys(buys, buys_path)


if __name__ == "__main__":
    main()
