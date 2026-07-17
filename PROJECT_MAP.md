# PROJECT_MAP.md — AI-readable project dictionary

**Read this before grepping.** Every module, script, and data artifact is indexed below.
Keep it current: when you add/move/rename files or change outputs, update this map in the same session.

## What this project is

A free-data, fully deterministic stock screener for a **2-year holding period**. No paid APIs, no
LLM, no network at score time.

```
Phase 1  Ingest             Yahoo movers + StockTwits + Reddit + Finviz + Capitol Trades → ticker pool
         (the only            → fetch prices/info/news (threaded) → snapshot to data/raw/<run_ts>/
          network phase)
Phase 2  Rule scoring       PURE function of the snapshot: 9 signals scored 0–10 → weighted composite
Phase 3  Rank + explain     deterministic sort; `reason` is a template built from the real drivers
Phase 4  CSV out            screener_<ts>.csv  (capped at --n)
```

**There is no second pass.** `TradingAgents_pipe.py` and `HedgeFund_pipe.py` were removed
2026-07-17 — too slow, and TradingAgents' Ollama runs **fabricated tool output** (`tasks/lessons.md`:
AMD quoted at $150–162 when AMD was $432; `fundamentals_report` 0 characters across all 46 saved
runs). Ollama is no longer part of this project at all. The screener is the whole product; the
Streamlit dashboard reads its snapshots.

**These are the pipeline's phases. `tasks/todo.md` uses "Phase 1–4" for the overhaul plan's
phases — different numbering, don't confuse them.**

`--replay <run_ts>` re-scores a saved snapshot with no network at all; `--ingest-only` stops after
the snapshot. Two replays of one snapshot produce a byte-identical CSV, and scoring is verified
pure by re-scoring with sockets blocked. That split is what makes tuning possible: you cannot A/B
two lexicons if re-scoring re-fetches a changed internet.

Under 20 Python files — the whole codebase is small enough to read, but start here.

## Directory map

| Path | Purpose |
|---|---|
| `market_screener/` | The screener package. **All its imports are flat (`from config import ...`) — you must run it with `market_screener/` as the working directory.** |
| `market_screener/sources/` | Universe seeding — one module per data source |
| `market_screener/scoring/` | One module per signal + `scorer.py` orchestrator |
| `market_screener/dashboard/` | **Streamlit dashboard — shipped and running (2026-07-17).** 5 tabs (Rankings, Ticker detail, Tracking, Diagnostics, Weight tuning). Reads snapshots for scoring; the Tracking tab reads the CSVs. Entry: `streamlit run dashboard/app.py` from anywhere |
| `market_screener/tracking/` | **Tracking tab back-end (2026-07-17).** Paper-trades each CSV's top picks per metric (cohort buy-and-hold) and follows forward returns to see which signal predicts gains. `cohorts.py` (build from CSVs) → `prices.py` (yfinance cache) → `returns.py` (live P/L, fixed-horizon, synthetic strategy). No persisted state |
| `market_screener/outputs_TA/<date>/` | **Where screener.py writes** (`config.output_dir`, cwd-relative). Capped at `--n`. The **Tracking tab reads these** — each CSV is a cohort; scoring still reads snapshots, not this |
| `market_screener/data/raw/<run_ts>/` | Snapshots (`config.snapshot_dir`): `prices.parquet`, `reference.parquet`, `info.json`, `news.json`, `reddit.json`, `stocktwits.json`, `capitol.json`, `meta.json`. **~46 MB per run** (`max` history for the 400 pool + 150 reference tickers). Replay and the dashboard read only these |
| `tasks/` | Workflow markdown per CLAUDE.md: `todo.md` (open work), `accomplished.md` (shipped + measurements), `lessons.md` (mistake rules) |
| Root | `CLAUDE.md`, `PROJECT_MAP.md`, `session_handoff.md` — docs only. No code lives at the root any more |

**Git repo as of 2026-07-17** (`git init` preceded the pipe removal so the deletions are
recoverable — commit `Baseline before the LLM-pipe removal`). Snapshots are gitignored: ~46 MB of
binary parquet each that no diff can describe.

`docs/MODULE_REFERENCE.md` and `graphify-out/` don't exist — **this file is the module reference**,
per CLAUDE.md.

## "Where do I look for…" quick index

| Task | Go to |
|---|---|
| Run the screener | `cd market_screener && python screener.py [--n 50]` (fetch + score) |
| **Re-score without the network** | `python screener.py --replay [RUN_TS]` — omit RUN_TS for the newest. `--ingest-only` stops after the snapshot |
| Any tunable knob (weights, windows, filters, lexicons) | `market_screener/config.py` — single `Config` dataclass, no YAML |
| Add/change a data source | `market_screener/sources/<source>.py`, then wire into `sources/__init__.py:seed_universe`. Needs a browser? use `sources/crawler.py`, don't grow a second copy |
| Add/change a signal | `market_screener/scoring/<signal>.py` → `scorer.py:_score_ticker` → `cfg.signal_weights` + `cfg.signal_categories` → `screener.py:signal_fieldnames`. **Anything needing the network belongs in `ingest.py`, not the scorer** |
| How a signal is calculated | **Signal taxonomy** section below |
| Debug Capitol Trades scraping | `market_screener/debug_capitol.py` (dumps raw crawl4ai markdown) |
| Design rationale / the locked decisions | `tasks/todo.md` — the grilled design lives there. (`market_screener_plan.md` was **deleted** 2026-07-17: it described 5 signals and a weekly horizon, both wrong) |
| **What is being built next + why** | **`tasks/todo.md`** — open work only. Phases 1-2 are done |
| **What already shipped + the measurements** | **`tasks/accomplished.md`** — Phase 1 (determinism) + Phase 2 (signal layer), with the numbers |
| Past mistakes / rules before coding | `tasks/lessons.md` |
| Last session's state | `session_handoff.md` (root) |

## market_screener/ module dictionary

**Entry + shared**

| Module | Purpose |
|---|---|
| `screener.py` | CLI entry. 4 phases, writes CSV + prints table. Flags: `--n`, `--output`, `--replay [RUN_TS]`, `--ingest-only` |
| `ingest.py` | **The only module that touches the network on a run.** `ingest(cfg, run_ts) -> Snapshot`: seeds the universe, fetches prices/info (threaded, retry → finviz fallback), drops the partial bar, fetches news for liquidity-gate survivors, resolves the finviz P/E fallback into `info["_finviz_trailingPE"]` |
| `snapshot.py` | `Snapshot` dataclass + `write_snapshot`/`load_snapshot`/`latest_run_ts`. Schema **`SCHEMA_VERSION=4`** (v4 added `st_sentiment` — per-ticker Bull/Bear counts in `stocktwits.json`); a version mismatch raises rather than guessing a migration. Carries `ingest_time` — the pinned clock every time-relative scorer reads |
| `config.py` | `Config` dataclass — every knob. Weights must sum to 1.0. No LLM keys remain (removed 2026-07-17 with the pipes) |
| `market_utils.py` | `is_market_open()` — 9:30–16:00 ET Mon–Fri. Called **once in ingest**, recorded as `meta.market_open_at_ingest`; calling it at score time made the partial-bar drop depend on replay time |

**sources/** — universe seeding

| Module | Fetches | Returns |
|---|---|---|
| `__init__.py` | `seed_universe(cfg) -> Seed` — calls all sources, whitelists, then `rank_pool` orders by source-confirmation count desc + ticker asc and caps at `seed_pool_size` | `Seed(pool: List[str], confirmations, st_ranks, reddit_counts, reddit_posts, capitol_trades)` |
| `crawler.py` | **Shared crawl4ai driver** (`scrape_urls`) — one headless-browser session + event-loop handling, used by `reddit.py` and `capitol_trades.py` | `[{url, status, html, markdown}]` |
| `ticker_universe.py` | `load_valid_tickers()` — NYSE/NASDAQ/AMEX symbol lists from GitHub (rreichel3/US-Stock-Symbols); Wikipedia fallback | whitelist `Set[str]` (~7,070) |
| `yahoo.py` | `fetch_yahoo_movers` via `yf.screen()` (most_actives, day_gainers, day_losers); `fetch_wikipedia_index` fallback (**needs `storage_options=_HEADERS`** — without it, 403 → 0) | ticker sets |
| `stocktwits.py` | `fetch_stocktwits_trending` (`trending/symbols.json`, discovery/buzz) + `fetch_stocktwits_sentiment` (`streams/symbol/<T>.json`, per-ticker Bull/Bear labels = `social_sentiment`). **via cloudscraper** — plain requests gets 403. Streams are budgeted (`stocktwits_stream_budget=200`, throttled) — ~200 req/hr unauth cap | trending: tickers + rank map (~30). streams: `{ticker: {bull, bear}}` |
| `reddit.py` | 8 subreddits × hot/new. **The `.json` API is 403 for every client incl. a browser; the old.reddit HTML page serves 200**, so it renders the listing via crawl4ai and reads `data-fullname`/`data-timestamp`/`class="title"`. Titles only — listing pages carry no `selftext` | posts + mention counts |
| `finviz.py` | `finviz` pkg Screener — most active, near 52w highs, avg vol >500k | ticker set |
| `capitol_trades.py` | crawl4ai scrape of capitoltrades.com, 3 pages ≈ 60 days | `{ticker: {buy_weight, sell_weight}}` |

Every source swallows its own exceptions and returns empty on failure — a dead source degrades the pool, it never crashes the run. **That is why every one of these was silently broken:** StockTwits, Reddit, and Wikipedia each returned 403 and each looked like "a quiet day".

**scoring/** — signals return 0–10 or **`None`**. `None` means unmeasured and renormalizes away; 5.0 is reserved for "measured, and average". Never impute.

| Module | Purpose | Weight |
|---|---|---|
| `scorer.py` | `score_all(snap, cfg, apply_filters=True)` — **pure**: no network, no clock, no threads. Two passes (percentiles and grade cuts need the peer group first), per-ticker renormalization, deterministic filters, sorts `(-composite_score, ticker)`. Public API the dashboard reuses: **`composite`** (weight sliders re-derive scores with it — never copy it), **`filter_reasons`** (every gate a row fails, named), **`passes_filters`** (= no reasons). `apply_filters=False` returns the unfiltered cross-section, needed because `coverage` is weight-dependent | — |
| `filters.py` | `price_of` / `avg_volume_of` / `passes_liquidity` — one definition, shared by ingest and scoring | — |
| `percentile.py` | `percentile_scores` (mid-rank, missing → `None`), `grouped_percentile_scores` (sector, pool-wide fallback), `score_against_reference` (fixed reference distribution → comparable across runs) | — |
| `metrics.py` | `sharpe` / `volatility` / `max_drawdown` / `ulcer_index` / `window`. Pure numpy; **matches quantstats to 0.00e+00 and is 4x faster** — see Gotchas for why quantstats is not a dependency | — |
| `ladder.py` | Excess sharpe vs SPY per window → grade cuts → letter → GPA. `build_grade_cuts` is **per-window** (pooled cuts let the 5y window structurally never award below C+) | — |
| `fundamentals.py` | `score_fundamentals_pool` — value/quality/growth, sector-relative percentile over 9 fields. `fetch_finviz_pe` is ingest-only | 0.45 |
| `monte_carlo.py` | `simulate` — bootstrap **with replacement**, 504d, seeded. Display + filter only. `simulate_terminal` returns the terminal-return array itself (same seed, same draws) so the dashboard can plot the distribution behind p_goal/p_bust without a second copy of the bootstrap | 0 |
| `news.py` | `fetch_news` (ingest, relevance-filtered + deduped) / `recent_weighted_count` | — |
| `sentiment.py` | `sentiment_score` = `5 + 5·rate·(n/(n+k))` — absolute, shrunk toward neutral | 0.10 |
| `volume.py` | `volume_ratio` — **display only**; "unusually active today" is attention, not 2-year risk | 0 |
| `capitol_hill.py` | net congressional buy pressure | 0.10 |
| `reason.py` | `build_reason` — deterministic template from the drivers that actually moved the rank | — |

**dashboard/** — **shipped and running** (2026-07-17). Reads snapshots via `load_snapshot` + `score_all`, never the CSV (which is capped at `--n`). Entry: `streamlit run market_screener/dashboard/app.py` from **anywhere** — `app.py` prepends `market_screener/` to `sys.path` AND `os.chdir`s to it, so flat imports and relative paths (`data/raw`) resolve regardless of launch cwd (Gotcha 2 no longer applies to the dashboard).

| Module | Purpose | State |
|---|---|---|
| `app.py` | Entry: sidebar run picker (schema-filtered), config-fingerprint score cache, `st.tabs`, **"Run screener for today"** button (drives `runner`), and the live ingest progress panel | shipped |
| `runner.py` | Launches `screener.py --ingest-only` as a subprocess (stdout→file, polled), so an in-app ingest runs off Streamlit's script thread; `finalize()` snaps the picker to the new snapshot | shipped |
| `data.py` | `@st.cache_resource` snapshot load + `@st.cache_data` scoring keyed on `(run_ts, cfg_fingerprint)`; `rescore`/`with_weights`/`split_filters`/`signal_stats`. `list_runs` **hides schema-incompatible snapshots** so the picker can't load a stale one | shipped |
| `tearsheet.py` | quantstats reports. **`_to_returns` is the only path to quantstats — feed it returns, never prices** (Gotcha 10). `verify_against_metrics` cross-checks every report against `scoring/metrics.py`. `render_tearsheet` is shared by the Ticker tab + Rankings click. **`figfmt="png"`** (SVG figures collide on element IDs when inlined together — Gotcha 11). `strategy_title=ticker` labels the report with the ticker, not "Strategy" | shipped |
| `views/table.py` | Rankings — full pool, sector/score/coverage filters, dropped-rows expander. **Single-row selectable**: clicking a symbol renders its tearsheet underneath | shipped |
| `views/ticker.py` | Grade ladder, signal breakdown vs pool, Monte Carlo distribution, tearsheet + window toggle. **Type-to-search box** filters the ticker list | shipped |
| `views/tracking.py` | Tracking tab UI: leaderboard (ranked by fixed-horizon excess-vs-SPY, falls back to live % until a cohort is a month old), toggleable comparison equity curve, per-bucket drill-down that **reuses `tearsheet.build_html`** on the bucket's synthetic NAV. Reads the `tracking/` back-end | shipped |
| `views/diagnostics.py` | Per-signal sd / distinct / fraction-pinned + coverage. The standing version of the check that caught the dead `news` constant | shipped |
| `views/weights.py` | Category weight sliders → live re-rank via `scorer.composite`, rank deltas vs the shipped prior | shipped |
| `__init__.py` (x2) | package markers | shipped |

**tracking/** — **shipped 2026-07-17.** The Tracking tab's back-end. Turns the date-stamped CSVs
into a paper-trading experiment: each CSV is a frozen cohort, its top picks per metric bought at the
CSV's `price_usd` (~$1000 each, whole shares, min 1) and held forever (no selling). Nothing is
persisted — cohorts rebuild from the CSVs, prices come from a yfinance cache. **Feed quantstats
returns, not prices** applies here too: a bucket's synthetic strategy is a return series turned into
a NAV, and `tearsheet.build_html` pct_changes it straight back (Gotcha 10).

| Module | Purpose |
|---|---|
| `cohorts.py` | Pure, network-free. `all_cohorts(cfg)` scans `outputs_TA/**/screener_*.csv`; each CSV → a `Cohort` of top-N `Position`s per metric (`cfg.tracking_buckets`). Direction is always highest score (for `max_drawdown`/`volatility`, the calmest names). Missing metric/price → row dropped from that bucket |
| `prices.py` | yfinance **adjusted** daily closes, cached one CSV per ticker under `cfg.tracking_cache_dir` (gitignored). Stale cache (>4 days old) refetched in full. The only view-time network in the app; screener determinism untouched |
| `returns.py` | Three measures: **live P/L** (CSV cost basis vs latest close), **fixed-horizon** return (yf-on-yf, `cfg.tracking_horizons` = 1/3/6/12mo, ranks the metrics), and a **synthetic daily return series** per bucket (equal-weight of open positions) → `nav()` → the tearsheet. `leaderboard`, `equity_curves`, `bucket_summary` |

**There is no LLM.** `llm/ranker.py` and `debug_llm.py` were deleted 2026-07-17. The model saw six numbers per ticker yet was asked to strip "meme spikes with no news catalyst" and "micro-caps" it could not see, so it narrated the dead `news` constant back as evidence. The CSV's `reason` column (renamed from `llm_reason`, which had become a lie) is `reason.build_reason` — it cannot hallucinate and costs nothing.

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

## Data artifacts

| File | Produced by | Consumed by |
|---|---|---|
| `market_screener/data/raw/<run_ts>/` | `ingest.py` | `--replay`, the dashboard. **The real artifact** — everything else is derived |
| `market_screener/outputs_TA/<date>/screener_<ts>.csv` | `screener.py` | you. An export, not an input |

**The snapshot is the artifact, not the CSV.** The CSV is truncated to `--n` (`screener.py:132` —
`scored[:cfg.n_results]`), so it holds 50 rows, not the 366 that passed filters. Anything that
wants the real pool loads the snapshot and calls `score_all` — which is free, because scoring is
pure and needs no network.

Screener CSV columns (2026-07-16 overhaul; `llm_reason` → `reason` on 2026-07-17):
`rank, ticker, composite_score, coverage, value, quality, growth, gold_score, max_drawdown, volatility, news_sentiment, social_sentiment, capitol_hill, gold_gpa, gold_worst, grades, windows_available, history_years, xs_3mo…xs_10y, divergence, meme_flag, news_buzz, social_buzz, rel_volume, max_drawdown_raw, volatility_raw, p_goal_2y, p_bust_2y, mc_confidence, sector, price_usd, reason, run_timestamp`.

Pre-overhaul CSVs are all deleted (2026-07-17). They were produced by a pipeline with a dead
`news` signal and a random pool cap, and nothing can read them: the schema guard that policed
them lived in `screener_csv.py`, which existed only to serve the two pipes and went with them.

## Gotchas

1. ~~**The screener's output and the pipelines' input are different directories.**~~ **Dissolved 2026-07-17** — with no pipes, there is no second reader to disagree with `config.output_dir`. Nothing consumes the CSV automatically now.
2. **`market_screener/` must be the working directory.** Imports are flat (`from config import Config`), so `python market_screener/screener.py` from the root fails. This applies to the dashboard too: `streamlit run dashboard/app.py` from inside `market_screener/`.
3. **Scoring must stay pure.** No network, no `time.time()`, no threads in `scoring/`. All three were live bugs (see Known bugs). Anything time-relative reads `snap.ingest_time`. To prove purity, block sockets and re-score — that is how the finviz call hiding inside `score_fundamentals` was caught.
4. **Failures are silent by design.** Sources catch everything and return empty. A dead source looks exactly like a quiet market — StockTwits, Reddit, and Wikipedia were each 403ing silently. **Check spread (`sd`, distinct count, fraction pinned at min/max) on a real pool before trusting any signal.**
5. **Changing the snapshot layout means bumping `SCHEMA_VERSION`** in `snapshot.py`. `load_snapshot` refuses a mismatch rather than guessing a migration. Currently **v4**; v1–v3 snapshots are unreadable. The dashboard's `data.list_runs` hides schema-incompatible runs so the picker can't load one.
6. **Snapshots are ~46 MB each** (`max` history for 400 pool + 150 reference tickers). They accumulate in `market_screener/data/raw/`. Prune old ones.
7. **Only `Close` and `Volume` are snapshotted.** No scorer reads OHLC, and dropping it keeps snapshots sane — but an OHLC-based signal would need a re-ingest.
8. ~~Model defaults disagree~~ — **dissolved 2026-07-17.** No model, no Ollama, no LLM keys in `config.py`.
9. `finviz` appears both as a seeding source and as an ingest fallback (info + P/E) — it's rate-limit-prone and blocking it degrades two phases at once.
10. **quantstats: feed it returns, never prices.** `qs.stats.max_drawdown` prepends a phantom baseline chosen by tier (`first_price > 10` → **100.0**), which joins the running peak — so any stock starting above $10 that trades below $100 gets a drawdown measured from a price it never traded at. Wrong for **44% of the real pool** (165/373, max error 78.5%); fed returns it is exact (0/373 wrong). See Known bugs.
11. **quantstats reports must use `figfmt="png"`, not the default SVG.** `qs.reports.html` inlines 14 matplotlib SVGs into one document; they share ~124 element IDs (clip-paths, glyphs) with ~1300 `<use href="#id">` refs that resolve document-wide to the FIRST match, so every plot after the first renders garbled/clipped. PNG figures are self-contained. Set in `dashboard/tearsheet.py:build_html`.

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
| **`quantstats.stats.max_drawdown` is wrong on prices — mechanism corrected 2026-07-17** | The old entry here said it "treats input as returns and compounds it". **It does not.** It prepends a *phantom baseline* and `_get_baseline_value` picks one by tier: `first_price > 1000` → `1e5`, `> 10` → **100.0**, else `1.0`. The baseline joins the running peak, so the drawdown is measured from a price the stock never traded at. KO 5y → **−54.40%** = `45.60/100 − 1` (true: **−17.3%**, 58.43 → 48.33 Oct 2023, hand-verified). MKL → **−98.6%** = `1395/1e5 − 1`. SPY/AAPL are *correct* only because they trade above 100. Real rule: **any stock starting above $10 that trades below $100 is wrong** — 165/373 of the pool (44%), max error 78.5%. **Fed returns it is exact: 0/373 wrong.** `qs.stats.montecarlo` is separately unusable (permutes returns → std 4.9e-15, binary `goal_probability`). quantstats is a **display-only** dependency (tearsheets); `scoring/metrics.py` stays the scoring path — it matches `sharpe`/`volatility` to 0.00e+00 at 4x the speed |
| **`social_sentiment` covers ~47% of the pool, budget-capped** | Now sourced from StockTwits stream Bull/Bear labels (schema v4), not the Reddit-title lexicon (which covered ~1.5%). Coverage = the top `stocktwits_stream_budget` (200) pool tickers that return labels; the tail renormalizes away. Resolves 2.6b/2.8b/2.8c — the label IS the signal, so there is no lexicon to validate. `news_sentiment` still uses the lexicon over Google-News headlines |
| **Weights are a guess** | 0.45/0.35/0.10/0.10 is an explicit prior, not a fitted result. Phase 3.4 fits them from IC once forward data exists; at a 2-year horizon that is years away, so interim reads are directional only |
| ~~Pool cap is random~~ | **Fixed 2026-07-16 (Phase 1.1).** Ranks by source-confirmation count desc, then ticker asc. Verified identical across 3 separate processes |
| ~~Ties are nondeterministic~~ | **Fixed 2026-07-16 (Phase 1.2).** Sorts `(-composite_score, ticker)`; scoring also dropped threads entirely, removing the root cause |
| ~~Wall clock / network at score time~~ | **Fixed 2026-07-16 (Phase 1.3).** `score_news` took `time.time()`, `_score_ticker` called `is_market_open()`, and `score_fundamentals` made a finviz call — all at score time. Now pinned into the snapshot; purity verified with sockets blocked |
| `volume` is **zero-inflated** | `volume.py:21` clips ratio<1 → 0.0, so any stock below its 20-day average volume ties at zero. **Real pool: 278/381 (73%)**, worse than the 11/20 first measured |
| `growth` saturates at +50% | `fundamentals.py:36` — DELL's earningsGrowth is 282%, pinned at 10.0 |
| `max_st_rank = 50` | `social.py:8` — StockTwits trending returns **30**, so last place scores 4.08 instead of ~0 |
| `quantstats.stats.montecarlo` is **unusable** | It *permutes* returns; `∏(1+r)` is permutation-invariant, so all sims share one terminal value (std 4.9e-15) and `goal_probability` is binary 0/1. Horizon is also locked to the input length |
| StockTwits trending | Returns 403 unauthenticated — **fixable**, see the `social` row above |
| ~~`debug_llm.py` + `market_screener_plan.md` say "five signals"~~ | **Dissolved 2026-07-17** — both files deleted rather than corrected |
| ~~`tradingagents==0.2.5` dep conflicts~~ | **Dissolved 2026-07-17** — package removed with the pipes. `tradingagents`, `langgraph`, `langchain-*` are no longer used by anything here and can be pip-uninstalled |
| ~~`market_screener/output/pipeline_results_*.csv`~~ | **Dissolved 2026-07-17** — directory deleted |
| CLAUDE.md references `docs/MODULE_REFERENCE.md` + `graphify-out/` | Neither exists; CLAUDE.md names PROJECT_MAP.md as the alternative, so read this file instead |

## Setup

```
pip install -r market_screener/requirements.txt     # yfinance, pandas, numpy, requests, finviz, lxml,
                                                    # html5lib, crawl4ai, cloudscraper, pyarrow, tzdata
python -m playwright install chromium               # crawl4ai needs a browser — Capitol Trades AND Reddit
```

`cloudscraper` (StockTwits' bot check) and `pyarrow` (snapshot parquet) are required, not optional.
**No Ollama, no LLM, no API keys** — the screener is fully local and deterministic.

`quantstats` is display-only (dashboard tearsheets) and ranks nothing — it is **not** in the
scoring path, and it must be fed **returns, never prices** (Gotcha 10).
