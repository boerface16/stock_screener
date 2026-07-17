# Accomplished

Completed work. One compact block per task/phase: outcome + headline metric + key files.

## Tracking tab — paper-trade the picks per metric, track forward returns (2026-07-17)

**Outcome:** New 5th dashboard tab that answers "which metric leads to the best returns." Each
date-stamped CSV becomes a frozen **cohort**: its top picks per metric are bought at the CSV's
`price_usd` (~$1000 each, whole shares, min 1 for >$1000 names) and held forever — cohort
buy-and-hold, no selling. 10 buckets: composite (top 10) + value/quality/growth/gold_score/
max_drawdown/volatility/news/social/capitol_hill (top 3 each). Grilled first (grill-me): every
load-bearing branch locked before coding.

**Design locked (grill 2026-07-17):** cohort buy-and-hold; ledger **derived from CSVs**, not
persisted; entry = CSV `price_usd`, current/history = **yfinance adjusted closes, cached**; equal-
weight avg % return; ranked by **fixed-horizon excess-vs-SPY** (1/3/6/12mo), with a live mark-to-
market view alongside; per-bucket deep-dive **reuses the quantstats tearsheet** (bucket = synthetic
strategy → NAV → `build_html`, so quantstats still gets returns, not prices — Gotcha 10 respected).

**Verified:** `AppTest` full-script run **0 exceptions**, Tracking leaderboard renders sorted
(Social +2.07% → Capitol Hill −1.37% on the one 2026-07-16 cohort). Live P/L **hand-checked**: EFC
72 sh, entry $13.70, close $13.485 → −$15.48 / −1.57%, matches to the cent. Only one CSV exists on
disk, so horizons are all still empty (cohort is 1 day old — correct, not a bug).

**In-app run now writes a CSV.** The "Run screener for today" button ran `screener.py
--ingest-only`, which snapshots but returns before scoring/CSV — so an in-app run never produced a
cohort. Changed `dashboard/runner.py` to spawn a **full** `screener.py` run (ingest + score + write
CSV), so every in-app run drops a dated CSV under `outputs_TA/` that the Tracking tab picks up.
Captions/toasts in `app.py` updated (~4–5 min now, since scoring is included).

**Key files:** `tracking/cohorts.py` (CSV→cohorts, pure), `tracking/prices.py` (yfinance cache),
`tracking/returns.py` (live / fixed-horizon / synthetic-strategy), `dashboard/views/tracking.py`
(leaderboard + equity curves + drill-down), `dashboard/runner.py` (full run, not `--ingest-only`),
`dashboard/app.py` (5th tab wired + captions), `config.py` (`tracking_*` knobs), `.gitignore`
(price_cache), `PROJECT_MAP.md` (tracking/ block). Full design in `tasks/todo.md` archived section.

## social_sentiment via StockTwits streams + 3 dashboard UX changes (2026-07-17)

**Outcome:** `social_sentiment` was populated for **6/396 (1.5%)** of the pool. Traced it (not a
bug): it rode on Reddit *titles*, and only 41/396 tickers appear in any Reddit title, of which only
6 contain a lexicon word. Replaced the source with StockTwits message-stream **Bull/Bear labels**
(poster-set, so counted not lexicon-scored). Coverage **6 → 186/396 (47%)**. Plus three dashboard
UX changes.

**Headline metrics:**
- `social_sentiment` non-None: **6 → 186** (47% of the scored pool), real values (MU 7.1, TSM 7.9).
- StockTwits stream coverage: **186/200 labeled** in the run (9 transient 503s, budget 200).
- **Determinism gate re-baselined on the v4 snapshot:** two replays of `20260717_135916`
  byte-identical (**16,145 bytes**). (Old 16,095/EFC-7.8847 baseline is retired — the composite
  moved because social now has real coverage; that's expected, not drift.)

**Social items (S):**
- `sources/stocktwits.py` `fetch_stocktwits_sentiment(cfg, tickers)` — streams `entities.sentiment.
  basic` → `{ticker: {bull, bear}}`, budgeted (`stocktwits_stream_budget=200`, confirmation-rank
  order so the budget spends on the most-corroborated names), throttled (`stocktwits_stream_delay`),
  stops on 429. Wired into `ingest.py` after the news gate.
- `snapshot.py` **SCHEMA_VERSION 3→4**: `st_sentiment` persisted in `stocktwits.json`
  (`{ranks, sentiment}`). `dashboard/data.list_runs` now hides schema-incompatible runs so the
  picker can't load a stale one.
- `scoring/sentiment.py` `score_from_counts(pos, neg, k)` (shrinkage from explicit counts;
  `sentiment_score` reuses it). `scoring/scorer.py`: social = labels; **Reddit-title lexicon path
  deleted** (resolves the weak `title.split()` matcher by removal). Reddit → buzz only.
- Resolves todo 2.6b/2.8b/2.8c: the label IS the signal, so there's no lexicon to validate.

**Dashboard UX items (U):**
- **U.0** Extracted the tearsheet block into `tearsheet.render_tearsheet(snap, cfg, ticker, run_ts,
  key_prefix)` — one impl, used by both the Ticker tab and the new rankings click.
- **U.1** Rankings `st.dataframe` is now `single-row` selectable; clicking a symbol renders its
  tearsheet underneath. `table.render(kept, dropped, snap, cfg, run_ts)`. Selection parsing handles
  both event shapes (verified) and maps `view.iloc[row]["ticker"]`.
- **U.2** `strategy_title=ticker` passed to `qs.reports.html` — verified the built report labels the
  column `MU` and the word "Strategy" is **absent** from the 698 KB output.
- **U.3** Ticker detail has a `st.text_input` search that substring-filters the list (verified:
  "MU" → MU/MUFG/MUR/TMUS). Empty = full list.

**Verified:** AppTest 0 exceptions across all 4 tabs on the v4 snapshot; picker shows v4 only; search
+ report-label + selection-mapping all exercised.

**Key files:** `sources/stocktwits.py`, `ingest.py`, `snapshot.py`, `config.py`,
`scoring/sentiment.py`, `scoring/scorer.py`, `dashboard/{data,tearsheet}.py`,
`dashboard/views/{table,ticker}.py`. `PROJECT_MAP.md` updated (schema v4, stocktwits row, social
coverage, list_runs filter).

## Dashboard — run the screener for today, from the app (2026-07-17)

**Outcome:** a **Run screener for today** button in the sidebar fetches today's market data and
writes a new snapshot, which the picker then loads and scores live — no terminal needed.

**How:** `dashboard/runner.py` launches `python screener.py --ingest-only` as a **subprocess**
(the real CLI ingest, so the app can't drift from what the screener writes), cwd pinned to
`market_screener/`. Chosen over an in-process `ingest()` call because ingest is a multi-minute
network phase driving crawl4ai (asyncio) + a thread pool, neither of which mixes with Streamlit's
rerun-per-interaction script thread. stdout → a **file**, not a PIPE, so a verbose child can't
deadlock on a full pipe buffer between reruns. `app.py` polls the log every 2s in a full-page
progress panel, and `runner.finalize()` snaps the run picker to the new snapshot the instant the
child exits.

**Verified end to end:** ran the real ingest (exit 0, wrote `data/raw/20260717_122109` — today),
then `AppTest` confirmed the dashboard defaults to that snapshot (newest of 3) and scores it —
**396 scored, 350 passed filters, 46 dropped, 0 exceptions.** Also confirmed the button, run
picker, and 4 tabs render with 0 exceptions before any ingest.

**Key files:** `market_screener/dashboard/runner.py` (new), `market_screener/dashboard/app.py`.

## PIVOT Phase B — Streamlit dashboard (2026-07-17)

**Outcome:** the screener has a UI. It reads snapshots (never the top-`--n` CSV), re-scores live,
and ranks nothing new — quantstats and Monte Carlo are display only. Six modules were written but
unrun at the last handoff; this session added the entry point + packaging and **ran it end to
end for the first time.** 0 exceptions.

**Headline metric:** `streamlit run dashboard/app.py` renders **4 tabs, 6 dataframes, 0 exceptions,
0 error boxes**; a cold score + Monte Carlo pass over the pool completes in ~16s and grade cuts
recalibrate normally (150 reference tickers). Verified with Streamlit's `AppTest` harness, which
runs the whole script — every tab, the quantstats tearsheet, and the live weight-rescore — in one
pass. The feared Arrow-on-`None`-column crash did not fire. Re-verified from the **project root**
(the user's failing cwd) after the chdir fix: **396 scored, 366 passed filters, 30 dropped**, 0
exceptions.

**Field bug caught + fixed (2026-07-17):** first launch outside `market_screener/` gave "No
snapshots under data/raw" — `snapshot_dir` is relative and the initial AppTest passed only because
its shell cwd was already `market_screener/`. Fixed by having `app.py` `os.chdir(_ROOT)` at
startup. Lesson logged: verify entry points from a realistic cwd.

**Items:**
- **B.8** `dashboard/app.py` — sidebar run picker, config fingerprint as the score cache key,
  `st.tabs` over the four views. Prepends `market_screener/` to `sys.path` **and `os.chdir`s to
  it**, so both flat imports (`from config import …`) and relative paths (`data/raw`) resolve no
  matter where `streamlit run` is launched. Ticker tab gets `kept + dropped` so dropped names stay
  inspectable; diagnostics/weights get the full unfiltered pool.
- **B.9** `dashboard/__init__.py` + `dashboard/views/__init__.py` — the views do
  `from dashboard import data`, which needs both packages importable.
- **B.10** `requirements.txt` += `streamlit>=1.56.0`, `quantstats>=0.0.81` (commented display-only,
  with the feed-it-returns rule).
- **B.11** Ran it. AppTest: 0 exceptions across all tabs.

**Key files:** `market_screener/dashboard/app.py` (entry), `dashboard/__init__.py`,
`dashboard/views/__init__.py`, `market_screener/requirements.txt`.

**Deferred (in todo.md):** (1) `st.components.v1.html` in `views/ticker.py` is deprecated
(removal targeted post-2026-06-01) — still works on 1.56, but the replacements take a URL/sanitized
HTML, not a scrollable srcdoc, so it needs a real fix not a rename. (2) The 4dp gate (dashboard
composite == CSV `composite_score`) has not been run. Scoring path untouched this session, so the
Phase A determinism gate (16,095 bytes, EFC 7.8847) is unaffected.

## PIVOT Phase A — LLM pipes removed (2026-07-17)

**Outcome:** the screener is the whole product. Both second-pass pipes and everything downstream
of them are gone — too slow, and TradingAgents' Ollama runs **fabricated tool output** (a
correctness failure, not a speed one). **Ollama, `tradingagents`, and every LLM key left the
project entirely.** Scoring is untouched: same snapshot in, same ranking out.

**Headline metrics:**
- **Determinism gate held:** two replays of snapshot `20260716_164333` → **byte-identical**
  (16,095 bytes). #1 still **EFC at 7.8847** — identical to the pre-removal result, so nothing
  in the scoring path moved.
- Repo **101 MB → 11 MB tracked** (90 MB of snapshots gitignored, ~10 MB of `ta_results/` deleted).
- Root went from 8 files + 5 output dirs to **3 docs + `market_screener/` + `tasks/`.** No code
  at the root at all.
- **2 gotchas and 3 known-bug rows dissolved** rather than being fixed — the code they described
  no longer exists.

**Items:**
- **A.0** `git init` + baseline commit *before* any deletion (was not a repo — deletions were
  unrecoverable). Snapshots gitignored: ~46 MB of binary parquet no diff can describe.
- **A.1/A.2** Deleted `TradingAgents_pipe.py`, `HedgeFund_pipe.py`, `screener_csv.py`,
  `market_screener/llm/`, `debug_llm.py`, and `outputs_hedge/`, `outputs_trading_agents/`,
  `reports/`, `results/`, `output/`, `market_screener/output/`.
- **A.3** Stripped `llm_model` / `ollama_base_url` / `thinking_mode` / `llm_candidate_multiplier`
  from `config.py`; removed the deprecated `--no-llm` no-op.
- **A.4** `llm_reason` → **`reason`** (CSV col 36). No LLM writes it — it is
  `reason.build_reason`, a deterministic template. The old name was a lie.
- **A.5** Deleted `market_screener_plan.md` (stale: "five signals", weekly horizon). **Beyond
  plan:** also deleted `market_screener/session_handoff.md` (an old handoff written entirely
  about the now-deleted Ollama ranker) and `outputs_TA/2026-05-15/` (a pre-overhaul CSV of the
  same unloadable class as the 11 in `output/`).
- **A.6** Reconciled `PROJECT_MAP.md`: rewrote the header/diagram, directory map, module
  dictionary, Data artifacts; deleted the Pipelines section; dissolved Gotchas 1 + 8; added
  Gotcha 10 (quantstats). Fixed a **live hazard** — the "add a signal" recipe still instructed
  future sessions to update `screener_csv.py:SIGNAL_COLS`, a file that no longer exists.

**The quantstats lesson was wrong about the mechanism — corrected.** `lessons.md` claimed
`qs.stats.max_drawdown` "treats input as returns and compounds prices". It does not: it prepends
a *phantom baseline* (`first_price > 10` → **100.0**; `> 1000` → `1e5`) that joins the running
peak, so the drawdown is measured from a price the stock never traded at. KO = `45.60/100 − 1` =
**−54.40%**, matching the observed number exactly; MKL = `1395/1e5 − 1` = **−98.6%**.

| Call | Wrong by >1pp (373 pool tickers) | Max error |
|---|---|---|
| `qs.stats.max_drawdown(prices)` | **165 / 373 (44%)** | **78.5%** |
| `qs.stats.max_drawdown(returns)` | **0 / 373 (0%)** | **0.0%** |

**quantstats was never broken — it was called wrong.** SPY/AAPL return correct answers (they
trade above 100), which is why a spot-check would have cleared it. Fed returns it is exact, so
the Phase B tearsheet is safe. `metrics.py` still stays the scoring path — that decision rested
on numpy being 4x faster and four one-liners not earning matplotlib+seaborn+scipy, which the
correction does not touch. New rule logged in `lessons.md`: *a measurement and an explanation of
it are two claims* — the wrong mechanism hid both the true blast radius (only $10–$100 stocks)
and the fix (feed it returns).

**Key files:** `PROJECT_MAP.md` (reconciled), `market_screener/config.py`, `screener.py`,
`tasks/lessons.md` (2 entries: 1 corrected, 1 new).

## Phase 1 — Foundation (2026-07-16)

**Outcome:** the screener is deterministic and re-scorable offline. Ingest and scoring are now
separate: `ingest.py` is the only module that touches the network, it writes a snapshot, and
`scoring/scorer.py` is a pure function of that snapshot. Tuning is now possible at all — the
precondition Phase 2 was blocked on.

**Headline metrics (measured, real 384-ticker pool, snapshot `20260716_144039`):**
- Two replays of one snapshot → **byte-identical CSV** (5,354 bytes each). Gate 1.4 met.
- `score_all` completes with **sockets blocked** — purity proven, not assumed. Gate 1.3 met.
- `rank_pool` in **3 separate processes → identical output**. Gate 1.1 met (the old
  `set(list(pool)[:400])` gave 3 different universes).
- Snapshot cost: **6.8 MB**, ingest ~2.5 min for 384 tickers.
- Refactor was behavior-preserving: output still reproduces every known bug exactly.

**Items:**
- **1.1** Pool cap now ranks by source-confirmation count desc, then ticker asc. Also a better
  cap: corroborated tickers survive instead of arbitrary ones.
- **1.2** Ties sort on `(-composite_score, ticker)`. Root cause also removed — scoring dropped
  the ThreadPoolExecutor entirely (pure arithmetic needs no threads), so completion order can
  no longer leak into ranks.
- **1.3/1.4** `snapshot.py` (Snapshot dataclass, schema v1, parquet + json, refuses version
  mismatch), `ingest.py`, `--replay [RUN_TS]` / `--ingest-only`.
- **1.5** `scoring/percentile.py` — `percentile_scores` (mid-rank, ties share a score, missing
  → `None` never 5.0, all-`None` below `min_peers`) + `grouped_percentile_scores` with
  pool-wide fallback for thin sectors.

**Three determinism bugs found during the work, beyond the two planned:**
- `news.py` computed its cutoff from `time.time()` **at score time** → the same snapshot scored
  differently on every replay. `score_news(items, now, lookback_days)` now takes `now` from
  `snapshot.ingest_time`.
- `scorer.py` called `is_market_open()` at score time → the partial-bar drop depended on what
  time of day you replayed. Resolved once in ingest, recorded as `meta.market_open_at_ingest`.
- `fundamentals.py` made a **network** finviz P/E call at score time. Ingest now resolves it
  into `info["_finviz_trailingPE"]`; the scorer is offline.

**Decision applied:** schema mismatch **fails loudly** (user's call, 2026-07-16). The two
byte-identical copies of `SIGNAL_COLS`/`find_latest_screener_csv`/`load_tickers` in both pipes
merged into `screener_csv.py` with a `validate_schema` guard — exits nonzero listing the missing
columns instead of writing blank cells via `extrasaction="ignore"`. Old May-2026 CSVs in
`output/` are now correctly unreadable rather than silently wrong.

**Risk retired — 1.5 sector depth.** Measured on the real 384 pool: **11 sectors, thinnest is
Real Estate at 9, and 0% of tickers sit in a sector below `min_peers=5`.** The earlier worry
("7 sectors, four with ≤2 names") was a 20-row sample artifact. Sector-relative percentile is
viable pool-wide; Phase 2.2 needs no special-casing.

**Key files:** `market_screener/ingest.py`, `market_screener/snapshot.py`,
`market_screener/scoring/{scorer,percentile,filters}.py`, `market_screener/sources/__init__.py`,
`screener_csv.py`, `market_screener/screener.py`.

**Would a staff ML engineer approve?** Yes with one caveat: the snapshot pins the *inputs*, but
`config.weights` still lives in code, so a replay reproduces a snapshot rather than a whole
experiment. Fine now (weights are an explicit guess until Phase 3.4 fits them from IC); revisit
when weight-fitting starts.

## Phase 2 (partial) — sources revived: 2.0, 2.6, Reddit (2026-07-16)

**Outcome:** all five discovery sources are alive at once for the first time. Every dead source
was a silently-swallowed 403.

| Source | Before | After |
|---|---|---|
| Yahoo movers | 271 | 271 |
| **StockTwits** | **0** (403) | **29** (cloudscraper) |
| **Reddit** | **0** (403) | **43** (crawl4ai) |
| Finviz | 26 | 26 |
| Capitol Trades | 118 | 118 (unchanged by the crawler refactor) |
| Pool | 384 | **400** (cap now binds) |

- **2.0 Wikipedia fallback:** `pd.read_html(url, storage_options=_HEADERS)`. **0 → 501 tickers**,
  matching its twin. The emergency pool parachute now opens.
- **2.6 StockTwits:** cloudscraper solves the bot check → 200, 29-30 symbols. Also retired the
  `max_st_rank=50` fossil — trending returns **30**, so `social.py` now derives last place from
  `max(st_ranks.values())` instead of a constant that cannot be right twice.
- **Reddit revived via crawl4ai** (user's call, and it worked). Its free `.json` API is 403 for
  every HTTP client *and* for a browser hitting the `.json` URL — but the ordinary old.reddit HTML
  page still serves 200. Now renders the listing and reads the DOM: **150 posts / 3 subs in 7.4s,
  100% carrying `created_utc`** (which 2.9 wants for recency). Trade-off recorded: listing pages
  carry titles only, so `selftext` is now empty and mentions come from titles alone.
- **New `sources/crawler.py`** — one crawl4ai driver shared by Reddit and Capitol Trades, instead
  of a second private copy of the browser + event-loop handling.

**Bug found by reviving Reddit — mention extraction was mostly English words.**
`_extract_tickers` upper-cased the text before running an all-caps regex, so every 2-5 letter word
became a candidate and `ON`/`OR`/`YOU`/`IT`/`UP`/`NOW` are all real tickers. Measured on 150 live
posts: **48 tickers, top 8 were English words → 17, essentially all real** (IBM, MRVL, ASML, NFLX,
MU, RKLB, ARM, RDDT, IBKR). Fixed by matching against the original text; noise list extended with
the modern vocabulary it predates (`AI` alone was 15 of 18 hits).

**Headline metric — `social` went from dead to working:**

| | sd | distinct | verdict |
|---|---|---|---|
| before | **0.00** | **1** | dead — all 381 at 0.0 |
| after | **1.32** | **31** | working (RKLB 8.76, UNH 8.11, SNDK 7.70, ASTS 7.60) |

339/394 still score 0, but that is correct rather than broken: only ~60 tickers are mentioned at
all, so the rest genuinely have no attention.

**Key files:** `market_screener/sources/{crawler,reddit,stocktwits,yahoo,capitol_trades}.py`,
`market_screener/scoring/social.py`, `market_screener/config.py` (`reddit_sort_orders`),
`market_screener/requirements.txt` (+cloudscraper, +pyarrow).

## Phase 2 — Signal layer rebuilt (2026-07-16)

**Outcome:** the composite is now fundamentals-led rather than attention-led, and the ranking is
unrecognisable — in the right direction.

| | Before | After |
|---|---|---|
| #1 | **SOBR, $1.05 penny stock** | **EFC** (15.7y, grades A-/B/B+/C+/C) |
| top 20 | ATAI, MAAS, penny/momentum names; ZTS at #19 with grades **F/F/F/F/C-** | JPM, MU, BAC, TSM, GOOG, NVDA, MS — long histories, real grades |
| composite sd | 0.58 | **0.98** |
| dead signals | `news` 84% saturated, `social` sd 0.00 | **none** — every ranking signal has real variance |

**Items:** 2.1 ladder ✅, 2.2 fundamentals x3 ✅, 2.3 risk metrics ✅, 2.5 Monte Carlo ✅,
2.7 news relevance ✅, 2.8 sentiment ✅ (v1, unvalidated), 2.9 buzz ✅, 2.10 filters ✅,
2.11 wire ✅. 400 → 367 survive the filters.

**2.1 — the ladder reproduces the plan's predictions on real data:**

| Check | Predicted | Measured |
|---|---|---|
| MU | straight A's | `A-/A/A/A/A` GPA 3.94 |
| MSFT | deteriorating, low | `C-/D+/C-/C+/A` GPA 2.20 — **last** |
| MSFT xs | −2.42/−2.32/−1.05/−0.37 | −2.62/−2.30/−1.07/−0.36 |
| window sd 3mo vs 5y | 1.63 vs 0.38 | **1.65 vs 0.40** — confirms per-window cuts are mandatory |
| % beating SPY | ~13% | 3mo 22%, 1y 13%, 2.5y 10%, 5y 15%, 10y 9% |

`period="max"` confirmed necessary: `"10y"` returns **2,513 bars** and the 10y window needs 2,520.

**The `xs → 0–10` open question dissolved.** It never needed a divisor: xs is mapped by the
recalibrated grade cuts → GPA → `gold_score = gpa/4*10`, which is exact and has no constant to
rot. No new fossil was created.

**2.7 gate met** — the five ambiguous tickers return their own news or zero, never someone
else's: AD → Array Digital Infrastructure (not Netflix ad revenue), **LINK → 0 articles**,
WRAP → Wrap Technologies (not "Markets Wrap"), PS → Pershing Square, CARE → Carter Bankshares.
Cost: zero extra requests — the company name was already in the `info` dict.

**Deviation from a locked decision: quantstats is NOT a dependency.** Measured first:
`sharpe` and `volatility` match my numpy versions to **0.00e+00** and mine are **4x faster**
(2,000 calls = 400 tickers x 5 windows). And `qs.stats.max_drawdown` **silently accepts prices
and returns garbage** — it treats input as returns and compounds it, giving KO −54% when the
true 5y drawdown is −17.3% (verified by hand: 58.43 → 48.33, Oct 2023). Four one-line formulas
did not justify a dependency chain of matplotlib + seaborn + scipy + tabulate, and its one
distinctive feature (`montecarlo`) was already rejected as unusable. `scoring/metrics.py`.

**Deviation: `momentum` dropped rather than replaced.** Plan item 2.4 said "momentum 12-1,
replace the 5-day z-score", but the plan's own taxonomy says momentum is subsumed by the ladder
(`xs_1y` already carries it). The taxonomy wins; 2.4 was stale. Revisit if Phase 3 IC disagrees.

**LLM removed from the ranking path** (locked decision). `llm_reason` is now a deterministic
template naming the drivers that actually moved the rank — it cannot hallucinate and costs
nothing. `--no-llm` is a deprecated no-op.

**Bug caught before it shipped: `gold_gpa` collision.** `_score_ticker` spread `**signals` then
`**gold`, and both defined `gold_gpa` — so the 0–4 report card silently overwrote the 0–10
ranking signal. The row disagreed with its own composite, and every reason read "weak vs-SPY
record 2.9" for a signal the composite scored 7.25. Split into `gold_score` (0–10, ranks) and
`gold_gpa` (0–4, display), plus a `collisions` guard that raises rather than letting a display
key ever overwrite a ranking signal again.

**Determinism survived all of it** — two replays byte-identical at schema v3, with the ladder,
recalibrated cuts, and a seeded Monte Carlo in the path.

**Cost:** snapshot 6.8 MB → **46 MB** (27 MB pool prices + 15 MB reference), ingest **2m04s** —
*faster* than the old 6mo run, because batching prices more than pays for the extra history.

**Key files:** `market_screener/scoring/{scorer,ladder,metrics,monte_carlo,fundamentals,news,
sentiment,percentile,reason,volume}.py`, `market_screener/{config,ingest,snapshot,screener}.py`,
`screener_csv.py` (SIGNAL_COLS updated → old CSVs now correctly fail the guard).

**Would a staff ML engineer approve?** The plumbing yes; the *calibration* is explicitly
unproven. Weights are a guess until Phase 3.4, and the sentiment lexicon has never been
validated against StockTwits' own labels — 2.8's gate. Nothing here is known to predict returns
yet; that is precisely what Phase 3 exists to find out.
