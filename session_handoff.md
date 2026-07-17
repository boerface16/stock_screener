# Session Handoff — Phases 1 + 2 implemented: determinism foundation + signal layer rebuilt

## Where it started
User asked to continue with "phase 1-4" of the signal-layer overhaul in `tasks/todo.md` (the
overhaul plan's phases, not the pipeline's — `PROJECT_MAP.md` uses the same numbers for a
different thing). Last session produced a grilled design and zero code. This session implemented
Phase 1 and Phase 2 end-to-end against live data. Phase 3 was scoped and deliberately not
started: 3.2-3.4 need forward returns that do not exist at a 2-year horizon.

## Decisions locked + what shipped

**User decisions this session**
- **Schema mismatch → fail loudly** (not shim, not archive). `A:\Stonks\Screener_Tool\screener_csv.py`
  validates the header and exits nonzero. The 11 pre-overhaul CSVs in `output\` now correctly
  fail to load; they stay where they are.
- **Reddit → use crawl4ai.** Correct call: the `.json` API is 403 for every HTTP client *and*
  for a browser hitting the `.json` URL, but the old.reddit HTML page serves 200.

**Phase 1 — Foundation (all gates met, `tasks/accomplished.md`)**
- Ingest/scoring split. `A:\Stonks\Screener_Tool\market_screener\ingest.py` is the only network
  module; `market_screener\scoring\scorer.py` is a pure function of the snapshot.
- `market_screener\snapshot.py` — Snapshot dataclass, `SCHEMA_VERSION` (now **3**), parquet+json,
  refuses version mismatch. `--replay [RUN_TS]` / `--ingest-only` in `screener.py`.
- Deterministic pool cap (`sources\__init__.py:rank_pool`, by source-confirmation count) and ties
  (`(-composite_score, ticker)`; scoring dropped threads entirely, removing the root cause).
- `market_screener\scoring\percentile.py` — the shared helper that retires the fossil-constant class.
- **3 determinism bugs found beyond the plan's 2:** `score_news` read `time.time()` at score time;
  `is_market_open()` was called per-thread; `score_fundamentals` made a live finviz call. All three
  pinned into the snapshot. The finviz one was only caught by re-scoring with sockets blocked.

**Phase 2 — Signal layer (2.0-2.11 done; 2.6b/2.8b/2.8c open)**
- All five discovery sources alive for the first time. StockTwits → cloudscraper (29). Reddit →
  crawl4ai on old.reddit HTML (43). Wikipedia fallback 0 → **501**. Capitol 118 unchanged.
- `sources\crawler.py` — one shared crawl4ai driver (Reddit + Capitol Trades).
- Ladder (`scoring\ladder.py`), fundamentals x3 sector-percentile (`scoring\fundamentals.py`),
  risk metrics (`scoring\metrics.py`), Monte Carlo (`scoring\monte_carlo.py`), news relevance
  (`scoring\news.py`), sentiment (`scoring\sentiment.py`), deterministic reason (`scoring\reason.py`).
- New taxonomy wired: FUNDAMENTALS 0.45 / PRICE-RISK 0.35 / DIRECTION 0.10 / INSIDER 0.10, with
  per-ticker renormalization and `coverage`. Attention is weight 0.00.
- **LLM removed from the ranking path.** `llm_reason` is now a deterministic template.
  `--no-llm` is a deprecated no-op; `llm/ranker.py` and `debug_llm.py` are orphaned.

**Deviations from locked decisions (both measured first, both recorded)**
- **quantstats is NOT a dependency.** `sharpe`/`volatility` match numpy to `0.00e+00`, numpy is 4x
  faster, and `qs.stats.max_drawdown` silently returns garbage on prices (KO −54% vs the true
  −17.3%, hand-verified 58.43 → 48.33 Oct 2023). Not in `requirements.txt`.
- **`momentum` dropped, not replaced** (old item 2.4). The plan's own taxonomy says the ladder
  subsumes it; 2.4 contradicted the taxonomy and was stale.

**Bug caught pre-ship:** `**signals` then `**gold` both defined `gold_gpa`, so the 0-4 report card
silently overwrote the 0-10 ranking signal — rows disagreed with their own composite. Split into
`gold_score` (ranks) / `gold_gpa` (display) + a collision guard that raises.

**Headline result:** #1 went from **SOBR, a $1.05 penny stock** to **EFC**; top 20 is now
JPM/MU/BAC/TSM/GOOG/NVDA. Composite sd 0.58 → 0.98. No dead signals. 400 → 366 pass filters.

## Key files for next session
- `A:\Stonks\Screener_Tool\tasks\todo.md` — **read first.** Open work only: Phase 2 leftovers
  (2.6b/2.8b/2.8c/2.3b), Phase 3, Phase 4, and the accepted risks.
- `A:\Stonks\Screener_Tool\tasks\accomplished.md` — **new this session.** What shipped + every
  measurement, incl. the two deviations and their evidence.
- `A:\Stonks\Screener_Tool\tasks\lessons.md` — 4 new patterns added (wall clock is an input; dead
  vs degraded source; normalising before matching; two dict keys one name; verify the library).
- `A:\Stonks\Screener_Tool\PROJECT_MAP.md` — reconciled this session.
- `A:\Stonks\Screener_Tool\market_screener\scoring\scorer.py` — the two-pass core; start here to
  understand the composite.
- `A:\Stonks\Screener_Tool\market_screener\config.py` — every knob, incl. `signal_weights`,
  `ladder_windows`, `grade_quantiles`, lexicons, filters.
- Plan file: none — `tasks/todo.md` drove this session.
- Memory files touched: none.
- PROJECT_MAP.md: **updated** — pipeline phases (ingest/replay + the Phase-numbering warning),
  directory map (`data/raw` row), Root row (`screener_csv.py`), quick-index rows (replay,
  add-a-signal, orphaned LLM rows, `accomplished.md`), module dictionary (`ingest`, `snapshot`,
  `config`, `market_utils`), sources table (`crawler`, `reddit`, `stocktwits`, `yahoo`), scoring
  table (rewritten for the new modules), Signal taxonomy section (replaced "Signal formulas"),
  CSV columns, Gotchas 1-9, Known bugs table, Setup.

## Running state
- Background processes: none
- Dev servers / ports: none
- Open worktrees / branches: none (not a git repo)
- **Environment:** `cloudscraper` + `pyarrow` are now required and are in
  `market_screener\requirements.txt`. `quantstats` was pip-installed in a *previous* session and
  is **deliberately unused** — safe to `pip uninstall quantstats`.
- **Snapshots on disk:** `market_screener\data\raw\20260716_163603` and `...\20260716_164333`
  (~45 MB each, schema v3, 90 MB total). All v1/v2 snapshots were deleted this session — they are
  unreadable by design.

## Verification — how to confirm things still work
- `cd A:\Stonks\Screener_Tool\market_screener && python screener.py --replay --no-llm --output f1.csv`
  then again with `--output f2.csv` — the two CSVs must be **byte-identical** (this is the
  determinism gate; it held at every schema version).
- `cd A:\Stonks\Screener_Tool\market_screener && python screener.py --n 12` — full run, ~2m10s,
  366 tickers pass filters, #1 EFC. Prints the recalibrated grade cuts.
- `python -c "from sources.yahoo import fetch_wikipedia_index; print(len(fetch_wikipedia_index()))"`
  — prints **501** (was 0).
- `python -c "import cloudscraper; print(len(cloudscraper.create_scraper().get('https://api.stocktwits.com/api/2/trending/symbols.json', timeout=20).json()['symbols']))"`
  — prints ~30.
- Scoring purity: load a snapshot, monkeypatch `socket.socket` to raise, call `score_all` — must
  complete. This is what caught the hidden finviz call.
- Schema guard: `python -c "import sys; sys.path.insert(0,'.'); from pathlib import Path; from screener_csv import load_tickers; load_tickers(Path(r'A:\Stonks\Screener_Tool\output\screener_20260515_105953.csv'),3)"`
  — must **exit 1** with "Schema mismatch".

## Deferred + open questions
- Open: **Build Phase 3.1 + the IC harness now, or stop?** — asked at end of session, unanswered.
  3.1 (`proj_log`) can ship today and start accumulating; 3.2/3.3/3.4 cannot produce a verdict
  because they need forward returns (years, at a 2y horizon).
- Open: **`social_sentiment` is missing for 360/367 rows** (todo 2.8c). Only ~45 tickers get Reddit
  mentions and few titles carry lexicon words, so it renormalizes away for ~98% of the pool.
  Decide: fill it via StockTwits streams (2.6b), or make DIRECTION news-only at 0.10.
- Deferred: **2.6b StockTwits streams → human bullish/bearish labels.** Blocks 2.8b. A 400-request
  burst is unproven (12 sampled).
- Deferred: **2.8b validate the sentiment lexicon.** v1 is shipped and carries 0.10 of the
  composite **on a guess** — the plan's gate (agreement vs StockTwits labels; DELL's −14% day
  scores < 4.0) has never been run.
- Deferred: `ulcer_index` implemented in `metrics.py` but unused (todo 2.3b).
- Accepted, unchanged: weights 0.45/0.35/0.10/0.10 are an explicit prior, not fitted. **Nothing in
  this screener is yet known to predict returns** — Phase 2 made it measurable, not proven.
- Accepted: Reddit `selftext` is gone (listing pages carry titles only), so mentions and social
  sentiment come from titles alone.
- Deferred (pre-existing): `HedgeFund_pipe.py` never run end-to-end; `tradingagents==0.2.5`
  dependency conflicts; TradingAgents' Ollama runs fabricate tool output.
- Deferred (pre-existing): screener writes `market_screener\outputs_TA\<date>\` but both pipes read
  `A:\Stonks\Screener_Tool\output\` — pass `--input` explicitly until reconciled.
- Deferred: `market_screener_plan.md` + `debug_llm.py` still say "five signals" and assume a weekly
  horizon; `llm/ranker.py` + `debug_llm.py` are now orphaned (todo Phase 4).

## Pick up here
Answer the open question: build Phase 3.1 (`proj_log` — every run's ranks + per-signal scores) so
forward-return measurement can start accumulating today, accepting that the 3.3 baseline gate
cannot return a verdict for months.
