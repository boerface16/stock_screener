# PROJECT_MAP.md — AI-readable project dictionary

**Read this before grepping.** Every module, script, and data artifact is indexed below.
Keep it current: when you add/move/rename files or change outputs, update this map in the same session.

## What this project is

A free-data stock screener plus two optional LLM "second-pass" pipelines, all running locally against
Ollama. No paid APIs.

```
Phase 1  Ingest             Yahoo movers + StockTwits + Reddit + Finviz + Capitol Trades → ticker pool
         (the only            → fetch prices/info/news (threaded) → snapshot to data/raw/<run_ts>/
          network phase)
Phase 2  Rule scoring       PURE function of the snapshot: 6 signals scored 0–10 → weighted composite
Phase 3  LLM cull           Ollama re-ranks top N×2 candidates → exactly N with a one-line reason
Phase 4  CSV out            screener_<ts>.csv
         ↓ (manual, --input)
Second pass (pick one)      TradingAgents_pipe.py  → BUY/SELL/HOLD per ticker
                            HedgeFund_pipe.py      → buy/sell action + quantity
```

**These are the pipeline's phases. `tasks/todo.md` uses "Phase 1–4" for the overhaul plan's
phases — different numbering, don't confuse them.**

`--replay <run_ts>` re-scores a saved snapshot with no network at all; `--ingest-only` stops after
the snapshot. Two replays of one snapshot produce a byte-identical CSV, and scoring is verified
pure by re-scoring with sockets blocked. That split is what makes tuning possible: you cannot A/B
two lexicons if re-scoring re-fetches a changed internet.

Only 24 Python files — the whole codebase is small enough to read, but start here.

## Directory map

| Path | Purpose |
|---|---|
| `market_screener/` | The screener package. **All its imports are flat (`from config import ...`) — you must run it with `market_screener/` as the working directory.** |
| `market_screener/sources/` | Universe seeding — one module per data source |
| `market_screener/scoring/` | One module per signal + `scorer.py` orchestrator |
| `market_screener/llm/` | Ollama cull/re-rank pass |
| `market_screener/outputs_TA/<date>/` | **Where screener.py actually writes** (`config.output_dir`, cwd-relative) |
| `market_screener/data/raw/<run_ts>/` | Snapshots (`config.snapshot_dir`): `prices.parquet`, `info.json`, `news.json`, `reddit.json`, `stocktwits.json`, `capitol.json`, `meta.json`. ~6.8 MB per 384-ticker run. Replay reads only these |
| `market_screener/output/` | Legacy screener output + `ta_results/` (TradingAgents' own per-ticker logs + yfinance cache) |
| `output/` | **Where both pipelines look for screener CSVs** (hardcoded absolute path). Contents are stale May 11–15 runs — see Gotchas |
| `outputs_trading_agents/<date>/` | TradingAgents_pipe.py results, buys, reasoning |
| `outputs_hedge/<date>/` | HedgeFund_pipe.py results, buys, reasoning |
| `reports/<TICKER>_<ts>/` | Not written by any file in this repo — external TradingAgents CLI output |
| `results/data_cache/` | Empty; TradingAgents default config artifact |
| `tasks/` | Workflow markdown per CLAUDE.md: `todo.md` (open work), `lessons.md` (mistake rules). `accomplished.md` not yet created — nothing has shipped |
| Root | `TradingAgents_pipe.py`, `HedgeFund_pipe.py`, `screener_csv.py` (shared CSV reader + schema guard for both pipes), `CLAUDE.md`, `market_screener_plan.md`, `session_handoff.md` |

Not a git repo. `docs/MODULE_REFERENCE.md` and `graphify-out/` don't exist — **this file is the
module reference for now**, per CLAUDE.md.

## "Where do I look for…" quick index

| Task | Go to |
|---|---|
| Run the screener | `cd market_screener && python screener.py [--n 50]` (fetch + score) |
| **Re-score without the network** | `python screener.py --replay [RUN_TS]` — omit RUN_TS for the newest. `--ingest-only` stops after the snapshot |
| Any tunable knob (weights, windows, filters, lexicons) | `market_screener/config.py` — single `Config` dataclass, no YAML |
| Add/change a data source | `market_screener/sources/<source>.py`, then wire into `sources/__init__.py:seed_universe`. Needs a browser? use `sources/crawler.py`, don't grow a second copy |
| Add/change a signal | `market_screener/scoring/<signal>.py` → `scorer.py:_score_ticker` → `cfg.signal_weights` + `cfg.signal_categories` → `screener.py:signal_fieldnames` → `screener_csv.py:SIGNAL_COLS`. **Anything needing the network belongs in `ingest.py`, not the scorer** |
| How a signal is calculated | **Signal taxonomy** section below |
| ~~LLM prompt / JSON parsing~~ | `market_screener/llm/ranker.py` — **no longer called.** Ranking is deterministic; kept only for reference |
| ~~Debug the LLM~~ | `market_screener/debug_llm.py` — **orphaned** by the same change (also still says "five signals") |
| Debug Capitol Trades scraping | `market_screener/debug_capitol.py` (dumps raw crawl4ai markdown) |
| Second-pass BUY/SELL analysis | `TradingAgents_pipe.py` (needs `tradingagents` pkg) |
| Second-pass portfolio actions | `HedgeFund_pipe.py` (needs `A:\Stonks\ai-hedge-fund` cloned + installed) |
| Design rationale / original spec | `market_screener_plan.md` (⚠ **stale**: describes 5 signals and a weekly horizon. Superseded by `tasks/todo.md`) |
| **What is being built next + why** | **`tasks/todo.md`** — open work only. Phases 1-2 are done |
| **What already shipped + the measurements** | **`tasks/accomplished.md`** — Phase 1 (determinism) + Phase 2 (signal layer), with the numbers |
| Past mistakes / rules before coding | `tasks/lessons.md` |
| Last session's state | `session_handoff.md` (root, current) and `market_screener/session_handoff.md` (older, LLM fix) |

## market_screener/ module dictionary

**Entry + shared**

| Module | Purpose |
|---|---|
| `screener.py` | CLI entry. 4 phases, writes CSV + prints table. Flags: `--n`, `--no-llm`, `--output`, `--model`, `--replay [RUN_TS]`, `--ingest-only` |
| `ingest.py` | **The only module that touches the network on a run.** `ingest(cfg, run_ts) -> Snapshot`: seeds the universe, fetches prices/info (threaded, retry → finviz fallback), drops the partial bar, fetches news for liquidity-gate survivors, resolves the finviz P/E fallback into `info["_finviz_trailingPE"]` |
| `snapshot.py` | `Snapshot` dataclass + `write_snapshot`/`load_snapshot`/`latest_run_ts`. Schema `SCHEMA_VERSION=1`; a version mismatch raises rather than guessing a migration. Carries `ingest_time` — the pinned clock every time-relative scorer reads |
| `config.py` | `Config` dataclass — every knob. Weights must sum to 1.0. Adds `price_history_period`, `snapshot_dir` |
| `market_utils.py` | `is_market_open()` — 9:30–16:00 ET Mon–Fri. Called **once in ingest**, recorded as `meta.market_open_at_ingest`; calling it at score time made the partial-bar drop depend on replay time |

**sources/** — universe seeding

| Module | Fetches | Returns |
|---|---|---|
| `__init__.py` | `seed_universe(cfg) -> Seed` — calls all sources, whitelists, then `rank_pool` orders by source-confirmation count desc + ticker asc and caps at `seed_pool_size` | `Seed(pool: List[str], confirmations, st_ranks, reddit_counts, reddit_posts, capitol_trades)` |
| `crawler.py` | **Shared crawl4ai driver** (`scrape_urls`) — one headless-browser session + event-loop handling, used by `reddit.py` and `capitol_trades.py` | `[{url, status, html, markdown}]` |
| `ticker_universe.py` | `load_valid_tickers()` — NYSE/NASDAQ/AMEX symbol lists from GitHub (rreichel3/US-Stock-Symbols); Wikipedia fallback | whitelist `Set[str]` (~7,070) |
| `yahoo.py` | `fetch_yahoo_movers` via `yf.screen()` (most_actives, day_gainers, day_losers); `fetch_wikipedia_index` fallback (**needs `storage_options=_HEADERS`** — without it, 403 → 0) | ticker sets |
| `stocktwits.py` | `api.stocktwits.com/.../trending/symbols.json` **via cloudscraper** — plain requests gets 403 | tickers + 1-based rank map (~30) |
| `reddit.py` | 8 subreddits × hot/new. **The `.json` API is 403 for every client incl. a browser; the old.reddit HTML page serves 200**, so it renders the listing via crawl4ai and reads `data-fullname`/`data-timestamp`/`class="title"`. Titles only — listing pages carry no `selftext` | posts + mention counts |
| `finviz.py` | `finviz` pkg Screener — most active, near 52w highs, avg vol >500k | ticker set |
| `capitol_trades.py` | crawl4ai scrape of capitoltrades.com, 3 pages ≈ 60 days | `{ticker: {buy_weight, sell_weight}}` |

Every source swallows its own exceptions and returns empty on failure — a dead source degrades the pool, it never crashes the run. **That is why every one of these was silently broken:** StockTwits, Reddit, and Wikipedia each returned 403 and each looked like "a quiet day".

**scoring/** — signals return 0–10 or **`None`**. `None` means unmeasured and renormalizes away; 5.0 is reserved for "measured, and average". Never impute.

| Module | Purpose | Weight |
|---|---|---|
| `scorer.py` | `score_all(snap, cfg)` — **pure**: no network, no clock, no threads. Two passes (percentiles and grade cuts need the peer group first), per-ticker renormalization, deterministic filters, sorts `(-composite_score, ticker)` | — |
| `filters.py` | `price_of` / `avg_volume_of` / `passes_liquidity` — one definition, shared by ingest and scoring | — |
| `percentile.py` | `percentile_scores` (mid-rank, missing → `None`), `grouped_percentile_scores` (sector, pool-wide fallback), `score_against_reference` (fixed reference distribution → comparable across runs) | — |
| `metrics.py` | `sharpe` / `volatility` / `max_drawdown` / `ulcer_index` / `window`. Pure numpy; **matches quantstats to 0.00e+00 and is 4x faster** — see Gotchas for why quantstats is not a dependency | — |
| `ladder.py` | Excess sharpe vs SPY per window → grade cuts → letter → GPA. `build_grade_cuts` is **per-window** (pooled cuts let the 5y window structurally never award below C+) | — |
| `fundamentals.py` | `score_fundamentals_pool` — value/quality/growth, sector-relative percentile over 9 fields. `fetch_finviz_pe` is ingest-only | 0.45 |
| `monte_carlo.py` | `simulate` — bootstrap **with replacement**, 504d, seeded. Display + filter only | 0 |
| `news.py` | `fetch_news` (ingest, relevance-filtered + deduped) / `recent_weighted_count` | — |
| `sentiment.py` | `sentiment_score` = `5 + 5·rate·(n/(n+k))` — absolute, shrunk toward neutral | 0.10 |
| `volume.py` | `volume_ratio` — **display only**; "unusually active today" is attention, not 2-year risk | 0 |
| `capitol_hill.py` | net congressional buy pressure | 0.10 |
| `reason.py` | `build_reason` — deterministic template from the drivers that actually moved the rank | — |

**llm/ranker.py** — **no longer in the ranking path.** The model saw six numbers per ticker yet was asked to strip "meme spikes with no news catalyst" and "micro-caps" it could not see, so it narrated the dead `news` constant back as evidence. Ranking is deterministic; `llm_reason` is now `reason.build_reason`. `--no-llm` is a deprecated no-op.

## Signal taxonomy — attention DISCOVERS, fundamentals SELECT

Attention (Yahoo/StockTwits/Reddit/Finviz) already decides who is in the pool, so weighting it again in the ranking counts it twice. It is **weight 0.00**.

```
FUNDAMENTALS  0.45   value, quality, growth              (3 x 0.15)
PRICE/RISK    0.35   gold_score 0.175, max_drawdown 0.0875, volatility 0.0875
DIRECTION     0.10   news_sentiment, social_sentiment    (2 x 0.05)
INSIDER       0.10   capitol_hill
```

**Weight 0 (display only):** `gold_gpa`, `gold_worst`, `grades`, `xs_3mo`…`xs_10y`, `divergence`, `meme_flag`, `history_years`, `windows_available`, `news_buzz`, `social_buzz`, `rel_volume`, `max_drawdown_raw`, `volatility_raw`, `p_goal_2y`, `p_bust_2y`, `mc_confidence`, `coverage`, `sector`.

| Signal | Formula | Normalization |
|---|---|---|
| value | P/E, P/S, EV/EBITDA — each `<=0` → `None` (a loss-making company has no interpretable P/E) | sector percentile, lower better |
| quality | profitMargins, ROE, D/E, currentRatio | sector percentile |
| growth | revenueGrowth, earningsGrowth | sector percentile |
| **gold_score** | `xs_<w> = sharpe(stock,w) − sharpe(SPY,w)` → per-window letter → `gold_gpa`/4·10 | **absolute** — the recalibrated cuts *are* the map, so no divisor can rot |
| max_drawdown / volatility | over `risk_window` (2.5y) | vs the **reference universe**, not the pool → comparable across runs |
| news/social_sentiment | `5 + 5·rate·(n/(n+k))`, `rate = (pos−neg)/(pos+neg)` | **absolute** (real zero); `k` stops n=1 scoring a 10 |
| capitol_hill | `5 + (buy_w·2 − sell_w·1)`, clipped | absolute |

`composite = Σ(w·signal) / Σ(w observed)` — **renormalized per ticker**, and `coverage` is that observed weight (the full set sums to 1.0).

**Filters** (deterministic, replacing the LLM's claimed noise removal): `min_price`, `min_avg_volume`, `min_coverage=0.40`, `max_drawdown_floor=-0.90`, `volatility_ceiling=2.50`, `p_bust_2y>0.40`, `min_history_years=1.0`. Real pool: 400 → 367 survive.

## Pipelines (root)

| File | Depends on | Reads | Writes |
|---|---|---|---|
| `TradingAgents_pipe.py` | `tradingagents` pkg (lazy-imported inside functions), Ollama | latest `output/screener_*.csv` | `outputs_trading_agents/<date>/ta_{results,buys}_<ts>.csv` + `ta_reasoning_<ts>.md`; TradingAgents' own logs → `market_screener/output/ta_results/` |
| `HedgeFund_pipe.py` | `A:\Stonks\ai-hedge-fund` (`sys.path.insert` → `from src.main import run_hedge_fund`), Ollama | same | `outputs_hedge/<date>/hf_{results,buys}_<ts>.csv` + `hf_reasoning_<ts>.md` |

Both: sort screener rows by `rank`, take top `--n`, emit a buys CSV only when there are buys. Key difference — TradingAgents loops ticker-by-ticker (`graph.propagate`, per-ticker timing, one failure doesn't stop the batch); HedgeFund passes all tickers to one `run_hedge_fund` call with a synthetic portfolio (`--cash`, default 1000), so one exception loses the whole batch and `elapsed_s` is just batch time ÷ ticker count.

`HedgeFund_pipe.py` validates the Ollama model up front (`/api/tags`) and exits with the available list if missing. `TradingAgents_pipe.py` does not.

## Data artifacts

| File | Produced by | Consumed by |
|---|---|---|
| `market_screener/outputs_TA/<date>/screener_<ts>.csv` | `screener.py` | nothing automatically — see Gotchas |
| `output/screener_<ts>.csv` (11 files, May 11–15) | older screener runs | `find_latest_screener_csv()` in both pipes |
| `outputs_trading_agents/<date>/*` | `TradingAgents_pipe.py` | you |
| `outputs_hedge/<date>/*` | `HedgeFund_pipe.py` | you |
| `market_screener/output/ta_results/<TICKER>/TradingAgentsStrategy_logs/*.json` | tradingagents internals (`results_dir`) | debugging |
| `market_screener/output/ta_results/data_cache/*-YFin-data-*.csv` | tradingagents yfinance cache | tradingagents |

Screener CSV columns (2026-07-16 overhaul — **the old schema no longer loads, by design**):
`rank, ticker, composite_score, coverage, value, quality, growth, gold_score, max_drawdown, volatility, news_sentiment, social_sentiment, capitol_hill, gold_gpa, gold_worst, grades, windows_available, history_years, xs_3mo…xs_10y, divergence, meme_flag, news_buzz, social_buzz, rel_volume, max_drawdown_raw, volatility_raw, p_goal_2y, p_bust_2y, mc_confidence, sector, price_usd, llm_reason, run_timestamp`.

`screener_csv.py:SIGNAL_COLS` must track `config.signal_weights`. The 11 pre-overhaul CSVs in `output/` now **fail loudly** on the guard rather than being scored with blank cells — they were produced by a pipeline with a dead `news` signal and a random pool cap.

## Gotchas

1. **The screener's output and the pipelines' input are different directories.** `screener.py` writes to `market_screener/outputs_TA/<date>/`, but both pipes read `screener_csv.SCREENER_OUTPUT_DIR` = `A:\Stonks\Screener_Tool\output\screener_*.csv` (flat, no date subdir) — and their `--help` text claims a third path, `market_screener/output/`. Auto-discovery therefore picks up a stale May-2026 CSV. **Always pass `--input` explicitly**, or fix `SCREENER_OUTPUT_DIR` / `config.output_dir` to agree. As of 2026-07-16 those stale CSVs now **fail loudly** on the schema guard rather than being scored with blank cells.
2. **`market_screener/` must be the working directory.** Imports are flat (`from config import Config`), so `python market_screener/screener.py` from the root fails.
3. **Scoring must stay pure.** No network, no `time.time()`, no threads in `scoring/`. All three were live bugs (see Known bugs). Anything time-relative reads `snap.ingest_time`. To prove purity, block sockets and re-score — that is how the finviz call hiding inside `score_fundamentals` was caught.
4. **Failures are silent by design.** Sources catch everything and return empty. A dead source looks exactly like a quiet market — StockTwits, Reddit, and Wikipedia were each 403ing silently. **Check spread (`sd`, distinct count, fraction pinned at min/max) on a real pool before trusting any signal.**
5. **Changing the snapshot layout means bumping `SCHEMA_VERSION`** in `snapshot.py`. `load_snapshot` refuses a mismatch rather than guessing a migration. Currently **v3**; v1/v2 snapshots are unreadable.
6. **Snapshots are ~46 MB each** (`max` history for 400 pool + 150 reference tickers). They accumulate in `market_screener/data/raw/`. Prune old ones.
7. **Only `Close` and `Volume` are snapshotted.** No scorer reads OHLC, and dropping it keeps snapshots sane — but an OHLC-based signal would need a re-ingest.
8. Model defaults disagree: `config.py` and `TradingAgents_pipe.py` use `gemma4:latest`; `HedgeFund_pipe.py` uses `qwen3.5:9b`. Only the pipes use the LLM now.
9. `finviz` appears both as a seeding source and as an ingest fallback (info + P/E) — it's rate-limit-prone and blocking it degrades two phases at once.

## Known bugs / stale docs

All of the following were measured on 2026-07-16 — see `tasks/todo.md` for the fixes and
`tasks/lessons.md` for the patterns. **Every one fails into a plausible-looking number**, which is
why none were visible from the output.

| Item | Status |
|---|---|
| `news` is **84% saturated** | `score_news` saturates at 8 weighted articles (a fossil from the `yf.Ticker().news` era, ~10 items); Google News RSS returns 100. **Corrected 2026-07-16:** the "sd = 0.00, a constant" claim was a 20-row artifact. On the real 384 pool: sd 1.29, 13 distinct, **321/381 (84%) pinned at 10.0**. Broken, but not literally constant. Phase 2.7 |
| ~~`social` is dead~~ | **Fixed 2026-07-16.** Both halves were 403. StockTwits → cloudscraper (29-30 symbols); Reddit → crawl4ai on the old.reddit HTML page (the `.json` API is 403 even for a browser). Measured **sd 0.00 / 1 distinct → sd 1.32 / 31 distinct**. `max_st_rank=50` fossil retired (trending returns 30 — now derived from the data). 339/394 still score 0, which is correct: only ~60 tickers are mentioned at all |
| ~~Reddit mentions are English words~~ | **Fixed 2026-07-16.** `_extract_tickers` upper-cased the text *then* ran an all-caps regex, so every 2-5 letter word became a candidate — `ON`/`OR`/`YOU`/`IT`/`UP`/`NOW` are all real tickers. **48 extracted → 17** once matched against the original text |
| ~~`fetch_wikipedia_index()` returns 0~~ | **Fixed 2026-07-16 (Phase 2.0).** `pd.read_html` needed the `storage_options` User-Agent its twin `ticker_universe.py` always passed. **0 → 501 tickers** |
| ~~`news` 84% saturated~~ | **Fixed 2026-07-16 (Phase 2.7).** Query is now the quoted company name (free — already in `info`) + `when:Nd`, with a relevance filter and syndication dedupe. Gate met: AD → Array Digital Infrastructure, LINK → **0**, WRAP → Wrap Technologies, PS → Pershing Square, CARE → Carter Bankshares. Article count is now `news_buzz` (display); the composite reads sentiment instead |
| ~~`volume` zero-inflated~~ | **Fixed 2026-07-16.** Left the composite entirely — it is attention, not 2-year risk. Emitted un-clipped as `rel_volume` (display), so the mapping destroys nothing |
| ~~`growth` saturates at +50%~~ | **Fixed 2026-07-16 (Phase 2.2).** Sector-relative percentile — no constant to rot. DELL's 282% is just the top of its sector now |
| **`quantstats.stats.max_drawdown` silently returns garbage on prices** | It treats input as *returns* and compounds it: KO 5y → **−54%** when the true drawdown is **−17.3%** (58.43 → 48.33, Oct 2023). It does not raise. `qs.stats.montecarlo` is separately unusable (permutes returns → std 4.9e-15, binary `goal_probability`). **quantstats is not a dependency** — `scoring/metrics.py` matches its `sharpe`/`volatility` to 0.00e+00 at 4x the speed |
| **Sentiment lexicon v1 is unvalidated** | Shipped and carrying 0.10 of the composite, but the plan's gate (agreement vs StockTwits' own bullish/bearish labels) has **never been run** — blocked on `streams/symbol/<T>.json`. `social_sentiment` is also missing for 360/367 rows. See `tasks/todo.md` 2.6b/2.8b/2.8c |
| **Weights are a guess** | 0.45/0.35/0.10/0.10 is an explicit prior, not a fitted result. Phase 3.4 fits them from IC once forward data exists; at a 2-year horizon that is years away, so interim reads are directional only |
| ~~Pool cap is random~~ | **Fixed 2026-07-16 (Phase 1.1).** Ranks by source-confirmation count desc, then ticker asc. Verified identical across 3 separate processes |
| ~~Ties are nondeterministic~~ | **Fixed 2026-07-16 (Phase 1.2).** Sorts `(-composite_score, ticker)`; scoring also dropped threads entirely, removing the root cause |
| ~~Wall clock / network at score time~~ | **Fixed 2026-07-16 (Phase 1.3).** `score_news` took `time.time()`, `_score_ticker` called `is_market_open()`, and `score_fundamentals` made a finviz call — all at score time. Now pinned into the snapshot; purity verified with sockets blocked |
| `volume` is **zero-inflated** | `volume.py:21` clips ratio<1 → 0.0, so any stock below its 20-day average volume ties at zero. **Real pool: 278/381 (73%)**, worse than the 11/20 first measured |
| `growth` saturates at +50% | `fundamentals.py:36` — DELL's earningsGrowth is 282%, pinned at 10.0 |
| `max_st_rank = 50` | `social.py:8` — StockTwits trending returns **30**, so last place scores 4.08 instead of ~0 |
| `quantstats.stats.montecarlo` is **unusable** | It *permutes* returns; `∏(1+r)` is permutation-invariant, so all sims share one terminal value (std 4.9e-15) and `goal_probability` is binary 0/1. Horizon is also locked to the input length |
| StockTwits trending | Returns 403 unauthenticated — **fixable**, see the `social` row above |
| `debug_llm.py` + `market_screener_plan.md` | Say "five signals"; production is six (`capitol_hill` added later). `llm/ranker.py` is correct |
| `tradingagents==0.2.5` deps | Conflicts with installed `langgraph`/`langchain-anthropic`/`rich` versions. Non-blocking; `langgraph-checkpoint-sqlite` pinned to 2.0.11 to fix a hard `ImportError` |
| `market_screener/output/pipeline_results_*.csv`, `trading_buys_*.csv` | Written by an older pipeline; nothing produces them now |
| CLAUDE.md references `docs/MODULE_REFERENCE.md` + `graphify-out/` | Neither exists; CLAUDE.md now names PROJECT_MAP.md as the alternative, so read this file instead. `tasks/` is planned |

## Setup

```
pip install -r market_screener/requirements.txt     # yfinance, pandas, numpy, requests, finviz, lxml,
                                                    # html5lib, crawl4ai, cloudscraper, pyarrow, tzdata
python -m playwright install chromium               # crawl4ai needs a browser — Capitol Trades AND Reddit
ollama serve                                        # localhost:11434 — only the second-pass pipes use it now
```

`cloudscraper` (StockTwits' bot check) and `pyarrow` (snapshot parquet) are required, not optional.
**quantstats is deliberately NOT a dependency** — see Known bugs.

TradingAgents and ai-hedge-fund are separate installs; see the docstring at the top of each pipe file.
