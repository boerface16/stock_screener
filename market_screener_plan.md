# Market Screener — Implementation Plan

A hybrid, free-data-only stock screener that seeds a dynamic universe, scores candidates across five signals, and uses a local Gemma4 LLM to cull noise before outputting a ranked CSV for downstream TradingAgents analysis.

---

## Goals

- Discover "interesting/hot" stocks on-demand (run once or twice a week)
- No paid APIs — all free data sources
- Output a tunable shortlist (default: 50 tickers) to CSV
- Feed output into TradingAgents (`ta.propagate()`) for deep-dive analysis

---

## Architecture Overview

```
Phase 1: Universe Seeding
  Yahoo Finance Movers ──┐
  StockTwits Trending   ──┼──► Raw Pool (200–500 tickers, capped at seed_pool_size)
  Reddit Ticker Mentions─┘

Phase 2: Rule-Based Scoring (parallel, 10 workers)
  Per-ticker: yfinance OHLCV + .info
  5 signals scored 0–10 each → weighted composite score
  Filters: min_price=$1.00, min_avg_volume=100k shares/day
  Sort descending → top N×2 candidates

Phase 3: Gemma4 LLM Cull Pass (Ollama, local)
  Input:  top N×2 candidates + all signal scores
  Tasks:  remove obvious noise, re-rank by holistic conviction
  Output: exactly N tickers + one-line reason each

Phase 4: CSV Output
  rank, ticker, composite_score, momentum, volume, news,
  social, fundamentals, price_usd, llm_reason, run_timestamp
```

---

## Data Sources (All Free, No Auth)

| Source | What It Provides | Method |
|---|---|---|
| Yahoo Finance screeners | Most active, gainers, losers, growth stocks | `yfinance` + requests |
| Wikipedia S&P 500 / NASDAQ 100 | Fallback index universe | `pd.read_html()` |
| StockTwits trending | Currently trending symbols + per-ticker retail sentiment | Public JSON API (no key) |
| Reddit | Ticker mentions from r/wallstreetbets, r/stocks, r/investing | Public JSON search API (no key) |
| yfinance OHLCV | Price history for momentum + volume scoring | `yfinance` |
| yfinance `.info` | P/E, revenue/earnings growth for fundamentals scoring | `yfinance` |
| yfinance `.news` | Article count + recency for news scoring | `yfinance` |

---

## Five Scoring Signals

All signals return a value from **0–10**.

### 1. Momentum (`momentum.py`)
- **Metric:** Z-score of the 5-day return vs. 90-day rolling daily-return σ
- **Mapping:** z = −4σ → 0, z = 0 → 5, z = +4σ → 10
- **Interpretation:** Higher = price moving unusually fast vs. its own history

### 2. Volume Anomaly (`volume.py`)
- **Metric:** Most-recent session volume ÷ 20-day average volume
- **Mapping:** 1× (normal) → 0, 3× → 5, 5×+ → 10
- **Interpretation:** Higher = possible institutional accumulation or unusual interest

### 3. News Activity (`news.py`)
- **Metric:** Weighted article count over last 7 days (articles within 2 days get 1.5× weight)
- **Mapping:** Saturates at 8 weighted articles → score 10
- **Interpretation:** Higher = event-driven catalyst present

### 4. Social Buzz (`social.py`)
- **Metric:** 60% Reddit mention count + 40% StockTwits trending rank
- **Reddit:** Saturates at 5 mentions → score 10
- **StockTwits:** Rank 1 → 10, Rank 50 → 0, not trending → 0
- **Interpretation:** Higher = retail sentiment ahead of price movement

### 5. Fundamentals (`fundamentals.py`)
- **Metric:** Revenue growth (35%) + Earnings growth (35%) + Trailing P/E valuation (30%)
- **P/E mapping:** <10 → 10 (cheap), 20 → 5 (fair), 40+ → 0 (expensive)
- **Interpretation:** Higher = business quality backing up the price action

---

## Composite Score

```
composite = w1×momentum + w2×volume + w3×news + w4×social + w5×fundamentals
```

### Default Weights (`config.py`)

| Signal | Weight | Rationale |
|---|---|---|
| Momentum | 0.25 | Strongest short-term predictive signal |
| Volume | 0.20 | Institutional footprint indicator |
| News | 0.20 | Catalyst presence reduces blind speculation |
| Social | 0.20 | Leading retail sentiment signal |
| Fundamentals | 0.15 | Noise filter; lowest weight since TradingAgents does the deep analysis |

### Weight Tuning Guide

| Goal | Adjustment |
|---|---|
| Focus on breakout / institutional plays | Increase `momentum` + `volume` |
| Reduce hype, improve hold quality | Increase `fundamentals` |
| Capture early retail sentiment | Increase `social` |
| Pure technicals + sentiment mode | Set `fundamentals: 0.0` |

> Weights must sum to 1.0.

---

## LLM Cull Pass — Gemma4

### Model
- **Model:** `gemma4:latest` (E4B variant — 4.5B effective / 8B with embeddings)
- **VRAM:** ~9.6 GB — fits comfortably in 16 GB with ~6 GB headroom for KV cache
- **Context window:** 128K tokens
- **Thinking mode:** enabled via `<|think|>` prepended to system prompt

### What the LLM Does
1. Receives top `N×2` rule-scored candidates with all signal values
2. **Removes** obvious noise: pure meme spikes, data artifacts, micro-caps with no news, suspiciously manipulated volume
3. **Re-ranks** survivors by holistic conviction across all five signals
4. **Returns** exactly N tickers as a JSON array with one-line reasons

### Why Pre-Fetch + Inject (Not Tool-Calling)
Following the same lesson learned in TradingAgents' Sentiment Analyst redesign: tool-calling LLMs fabricate data under prompt pressure when the data is missing. All signal scores are computed deterministically **before** the LLM is invoked. The LLM's only job is structured triage — it never fetches data.

### Fallback Behavior
If Ollama is unavailable or returns malformed output, the script automatically falls back to composite-score ordering. The script never crashes.

---

## File Structure

```
market_screener/
├── screener.py              # main entry point
├── config.py                # all tunable parameters
├── requirements.txt
├── sources/
│   ├── __init__.py
│   ├── yahoo.py             # Yahoo Finance screeners + index fallbacks
│   ├── stocktwits.py        # StockTwits trending symbols
│   └── reddit.py            # Reddit post fetcher + ticker extractor
├── scoring/
│   ├── __init__.py
│   ├── momentum.py
│   ├── volume.py
│   ├── news.py
│   ├── social.py
│   ├── fundamentals.py
│   └── scorer.py            # per-ticker orchestrator (parallel)
├── llm/
│   ├── __init__.py
│   └── ranker.py            # Gemma4 cull + rank via Ollama
└── output/
    └── screener_YYYYMMDD_HHMMSS.csv
```

---

## Configuration Reference (`config.py`)

| Key | Default | Description |
|---|---|---|
| `n_results` | `50` | Number of tickers in final CSV |
| `llm_model` | `gemma4:latest` | Ollama model name |
| `ollama_base_url` | `http://localhost:11434` | Ollama server URL |
| `thinking_mode` | `True` | Enable Gemma4 `<|think|>` reasoning |
| `weights` | see above | Signal weights dict |
| `lookback_days` | `7` | News + social lookback window |
| `momentum_window` | `5` | Days for recent return calculation |
| `momentum_baseline` | `90` | Days for rolling σ baseline |
| `volume_avg_window` | `20` | Days for average volume baseline |
| `seed_pool_size` | `400` | Cap on raw candidate pool |
| `llm_candidate_multiplier` | `2` | `n_results × this` sent to LLM |
| `min_price` | `1.0` | Minimum share price (filters penny stocks) |
| `min_avg_volume` | `100,000` | Minimum avg daily volume (filters illiquid names) |
| `reddit_subreddits` | `[wallstreetbets, stocks, investing]` | Subreddits to scan |
| `reddit_limit_per_sub` | `50` | Posts fetched per subreddit |
| `reddit_min_mentions` | `1` | Minimum Reddit mentions to include a ticker |
| `max_workers` | `10` | Parallel scoring threads |
| `request_timeout` | `10` | Seconds per HTTP call |

---

## Output CSV Schema

| Column | Description |
|---|---|
| `rank` | Final LLM-assigned rank (1 = best) |
| `ticker` | Ticker symbol |
| `composite_score` | Weighted composite (0–10) |
| `momentum` | Momentum signal score (0–10) |
| `volume` | Volume anomaly score (0–10) |
| `news` | News activity score (0–10) |
| `social` | Social buzz score (0–10) |
| `fundamentals` | Fundamentals score (0–10) |
| `price_usd` | Share price at time of scoring |
| `llm_reason` | One-line Gemma4 conviction statement |
| `run_timestamp` | YYYYMMDD_HHMMSS of the run |

---

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Pull Gemma4 via Ollama (one-time)
ollama pull gemma4

# Run with defaults (50 tickers, LLM on)
python screener.py

# Common overrides
python screener.py --n 30               # smaller list
python screener.py --no-llm             # pure rule-based, much faster
python screener.py --output picks.csv   # custom output filename
python screener.py --model gemma4:26b   # override model
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Reddit posts fetched once | Reused for both universe seeding and social scoring — avoids double-hitting Reddit's ~10 req/min rate limit |
| Thinking mode enabled | Gemma4 reasons internally before committing to JSON — improves noise filtering quality |
| LLM fallback to composite score | Script never crashes; worst case is composite-score ordering |
| Weights in `config.py` | No code changes needed to adjust signal priority — just edit numbers and rerun |
| `--no-llm` flag | Fast iteration and testing without waiting for local inference |
| Pre-compute all scores before LLM | LLM never fetches data — eliminates hallucination risk for signal values |

---

## Next Steps

- [ ] Wire CSV output into `ta.propagate()` loop for full TradingAgents analysis
- [ ] Add sector-level P/E comparison for more accurate fundamentals scoring
- [ ] Add options flow signal (unusual call/put activity) if a free source becomes available
- [ ] Experiment with `gemma4:26b` if VRAM is upgraded beyond 20 GB
