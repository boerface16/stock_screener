# Accomplished

Completed work. One compact block per task/phase: outcome + headline metric + key files.

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
