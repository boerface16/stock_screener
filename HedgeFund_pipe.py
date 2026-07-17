"""
Second-pass pipeline: feed market_screener top-N tickers through ai-hedge-fund (Ollama)
and output results into a date-partitioned outputs_hedge folder.

Setup (one-time):
    git clone https://github.com/virattt/ai-hedge-fund A:\\Stonks\\ai-hedge-fund
    cd A:\\Stonks\\ai-hedge-fund && pip install -e .
    copy .env.example .env  # set OLLAMA_BASE_URL, leave FINANCIAL_DATASETS_API_KEY blank

Usage:
    python HedgeFund_pipe.py [--n 40] [--model qwen3.5:9b] [--date 2026-05-14]
                             [--start-date 2026-02-14] [--input path/to/screener.csv]
                             [--analysts ben_graham,cathie_wood] [--cash 1000]
                             [--show-reasoning]
"""

import argparse
import csv
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

AI_HEDGE_FUND_DIR = Path(r"A:\Stonks\ai-hedge-fund")
sys.path.insert(0, str(AI_HEDGE_FUND_DIR))

from screener_csv import SIGNAL_COLS, find_latest_screener_csv, load_tickers

OUTPUT_HEDGE_DIR = Path(__file__).parent / "outputs_hedge"

RESULT_FIELDNAMES = [
    "date", "rank", "ticker", "price_usd", "composite_score",
    "hf_action", "hf_quantity", "elapsed_s", "hf_reasoning",
]


def validate_ollama_model(model: str) -> None:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        available = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        sys.exit(f"Cannot reach Ollama at localhost:11434 — is it running? ({e})")
    if model not in available:
        sys.exit(
            f"Model '{model}' not found in Ollama.\n"
            f"Available models: {available}\n"
            f"Pull it with: ollama pull {model}"
        )


def write_results(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"Results written to {output_path}")


def write_buys(buys: list[dict], output_path: Path) -> None:
    fieldnames = [
        "rank", "ticker", "composite_score",
        *SIGNAL_COLS,
        "price_usd", "screener_reason", "hf_action", "hf_quantity", "hf_reasoning",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(buys)
    print(f"Buy list written to {output_path}")


def write_reasoning(
    results: list[dict],
    analyst_signals: dict,
    output_path: Path,
    run_date: str,
    provider: str,
    model: str,
    timestamp: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# HedgeFund Analysis — {run_date}",
        f"Model: {provider}/{model}  |  Run: {timestamp}",
        "",
    ]
    for row in results:
        ticker = row["ticker"]
        lines.append(f"## {ticker}")
        action = row.get("hf_action", "N/A")
        qty = row.get("hf_quantity", "N/A")
        reasoning = row.get("hf_reasoning", "")
        lines.append(f"**Decision:** {action} {qty} shares")
        lines.append(f"**Reasoning:** {reasoning}")
        lines.append("")

        ticker_signals = analyst_signals.get(ticker, {})
        if ticker_signals:
            lines.append("### Analyst Signals")
            for analyst, signal_data in ticker_signals.items():
                if isinstance(signal_data, dict):
                    signal = signal_data.get("signal", "")
                    confidence = signal_data.get("confidence", "")
                    reasoning_text = signal_data.get("reasoning", "")
                    lines.append(f"- **{analyst}**: {signal} (confidence: {confidence}) — {reasoning_text[:200]}")
                else:
                    lines.append(f"- **{analyst}**: {signal_data}")
        lines.append("")
        lines.append("---")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Reasoning written to {output_path}")


def print_table(results: list[dict]) -> None:
    if not results:
        return
    header = f"{'Rank':>4}  {'Ticker':<6}  {'Price':>8}  {'Score':>10}  {'Action':<8}  {'Qty':>6}  Reasoning"
    print("\n" + "=" * 100)
    print(header)
    print("-" * 100)
    for row in results:
        reasoning = row.get("hf_reasoning", "")[:45]
        price = row.get("price_usd", "")
        try:
            price_fmt = f"${float(price):>7.2f}"
        except (ValueError, TypeError):
            price_fmt = f"{'N/A':>8}"
        action = row.get("hf_action", "ERROR")
        qty = row.get("hf_quantity", "")
        print(
            f"{row['rank']:>4}  {row['ticker']:<6}  {price_fmt}  "
            f"{float(row['composite_score']):>10.4f}  "
            f"{action:<8}  {str(qty):>6}  {reasoning}"
        )
    print("=" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ai-hedge-fund second-pass on screener output")
    parser.add_argument("--n", type=int, default=40, help="Number of top tickers to analyze (default 40)")
    parser.add_argument("--model", default="qwen3.5:9b", help="Ollama model name (default qwen3.5:9b)")
    parser.add_argument("--date", default=str(date.today()), help="Analysis end date YYYY-MM-DD (default today)")
    parser.add_argument("--start-date", default=None, help="Analysis start date YYYY-MM-DD (default 3 months before --date)")
    parser.add_argument("--input", default=None, help="Path to screener CSV (default: latest in market_screener/output/)")
    parser.add_argument("--analysts", default="", help="Comma-separated analyst keys (default: all)")
    parser.add_argument("--cash", type=float, default=1000.0, help="Starting portfolio cash (default 1000)")
    parser.add_argument("--provider", default="Ollama", help="Model provider (default Ollama)")
    parser.add_argument("--show-reasoning", action="store_true", help="Pass show_reasoning=True to run_hedge_fund")
    args = parser.parse_args()

    # Resolve start date
    if args.start_date is None:
        from datetime import datetime as dt
        end = dt.strptime(args.date, "%Y-%m-%d")
        args.start_date = str((end - timedelta(days=90)).date())

    # Validate model before doing anything expensive
    if args.provider.lower() == "ollama":
        validate_ollama_model(args.model)

    input_path = Path(args.input) if args.input else find_latest_screener_csv()
    print(f"Loading screener results from: {input_path}")

    tickers = load_tickers(input_path, args.n)
    ticker_symbols = [r["ticker"] for r in tickers]
    print(f"Analyzing top {len(tickers)} tickers: {ticker_symbols}")
    print(f"Date range: {args.start_date} → {args.date}  |  Model: {args.provider}/{args.model}")
    print(f"Portfolio cash: ${args.cash:,.0f}  |  Show reasoning: {args.show_reasoning}")

    analysts = [a.strip() for a in args.analysts.split(",") if a.strip()] if args.analysts else []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_HEDGE_DIR / args.date
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / f"hf_results_{timestamp}.csv"
    buys_path = output_dir / f"hf_buys_{timestamp}.csv"
    reasoning_path = output_dir / f"hf_reasoning_{timestamp}.md"

    portfolio = {
        "cash": args.cash,
        "margin_requirement": 0.0,
        "positions": {
            t: {"long": 0, "short": 0, "long_cost_basis": 0.0, "short_cost_basis": 0.0}
            for t in ticker_symbols
        },
        "realized_gains": {t: 0.0 for t in ticker_symbols},
    }

    print(f"\nRunning ai-hedge-fund on {len(tickers)} tickers...")
    batch_start = time.time()

    try:
        from src.main import run_hedge_fund
        result = run_hedge_fund(
            tickers=ticker_symbols,
            start_date=args.start_date,
            end_date=args.date,
            portfolio=portfolio,
            show_reasoning=args.show_reasoning,
            selected_analysts=analysts,
            model_name=args.model,
            model_provider=args.provider,
        )
        decisions = result.get("decisions", {})
        analyst_signals = result.get("analyst_signals", {})
    except Exception:
        traceback.print_exc()
        decisions = {}
        analyst_signals = {}

    batch_elapsed = time.time() - batch_start
    per_ticker_elapsed = round(batch_elapsed / max(len(tickers), 1), 1)

    all_results = []
    buys = []
    for row in tickers:
        ticker = row["ticker"]
        decision = decisions.get(ticker, {})
        action = str(decision.get("action", "ERROR")).lower() if decision else "error"
        quantity = decision.get("quantity", 0)
        reasoning = str(decision.get("reasoning", ""))[:500]
        result_row = {
            **row,
            "date": args.date,
            "screener_reason": row.get("llm_reason", ""),
            "hf_action": action,
            "hf_quantity": quantity,
            "hf_reasoning": reasoning,
            "elapsed_s": per_ticker_elapsed,
        }
        all_results.append(result_row)
        if action == "buy":
            buys.append(result_row)

    mins, secs = divmod(int(batch_elapsed), 60)
    print(f"\nDone. {len(buys)} BUY action(s) out of {len(tickers)} analyzed.  Total time: {mins}m {secs}s")
    print_table(all_results)

    write_results(all_results, results_path)
    write_reasoning(all_results, analyst_signals, reasoning_path, args.date, args.provider, args.model, timestamp)
    if buys:
        write_buys(buys, buys_path)
    else:
        print("No BUY actions found in this batch.")


if __name__ == "__main__":
    main()
