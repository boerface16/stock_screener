# TODO

## PIVOT — drop the LLM pipes, build a Streamlit dashboard

Decided 2026-07-17. The two second-pass pipes are cut: too slow, and TradingAgents' Ollama runs
**fabricate tool output** (`lessons.md` — AMD at $150-162 when AMD was $432; `fundamentals_report`
0 characters across all 46 saved runs). That is a correctness failure, not a speed one. Nothing
downstream of the screener survives. Ollama leaves the project entirely — the LLM already left the
ranking path last session.

This absorbs Phase 4 (docs) and dissolves Gotcha 1 (the screener writes `outputs_TA/`, the pipes
read `output/`) — with no pipes, there is no second reader to disagree with.

### The quantstats lesson was wrong about the mechanism — corrected 2026-07-17

`lessons.md` says `qs.stats.max_drawdown` "treats its input as returns, so passing it prices makes
it compound prices". **That is not what happens.** Read the source: it prepends a *phantom
baseline* and `_get_baseline_value` picks it by tier — `first_price > 1000` → `1e5`,
`first_price > 10` → **100.0**, else `1.0`. The baseline joins the running peak, so the drawdown
is measured from a price the stock never traded at.

The real rule: **any stock starting above $10 that trades below $100 gets a fabricated drawdown.**

| | |
|---|---|
| KO 5y, hand-computed | **−17.27%** (58.43 → 48.33 @ 2023-10-05) — `metrics.py` matches exactly |
| KO 5y, `qs` on prices | **−54.40%** = `45.60/100 − 1` — the phantom baseline *is* the bug |
| MKL 2.5y, `qs` on prices | **−98.6%** = `1395/1e5 − 1` — starts at $1410, so it gets the 1e5 tier |
| SPY / AAPL | **correct** — they trade *above* 100, so the baseline never becomes the peak |

Measured on the real pool (373 tickers with full 2.5y history, snapshot `20260716_164333`):

| Call | Wrong by >1pp | Max error |
|---|---|---|
| `qs.stats.max_drawdown(prices)` | **165 / 373 (44%)** | **78.5%** |
| `qs.stats.max_drawdown(returns)` | **0 / 373 (0%)** | **0.0%** |

**quantstats is not broken — it was called wrong.** Fed returns (its documented contract) it is
exact. So the tearsheet is safe, under one hard rule: **feed it returns, never prices.**

What does *not* change: `metrics.py` stays the scoring path. Its justification never rested on the
drawdown bug — numpy matches `sharpe`/`volatility` to 0.00e+00 and is 4x faster, and four one-line
formulas do not earn matplotlib + seaborn + scipy + tabulate. quantstats returns as a
**display-only** dependency, ranking nothing.

### Phase A — Removal

- [ ] **A.0 `git init` first.** Not a git repo, so every deletion below is unrecoverable. Commit
      the current tree before removing anything.
- [ ] **A.1 Delete the pipes + orphans.** `TradingAgents_pipe.py`, `HedgeFund_pipe.py`,
      `screener_csv.py` (it exists *only* to serve the two pipes), `market_screener/llm/`,
      `market_screener/debug_llm.py` (both already orphaned last session).
- [ ] **A.2 Delete their outputs.** `outputs_hedge/`, `outputs_trading_agents/`, `reports/`,
      `results/`, `output/` (11 pre-overhaul CSVs that already fail the schema guard),
      `market_screener/output/` (~10 MB of `ta_results/` + a yfinance cache).
- [ ] **A.3 Strip LLM config.** `config.py`: `llm_model`, `ollama_base_url`, `thinking_mode`,
      `llm_candidate_multiplier`. `screener.py`: the deprecated `--no-llm` no-op.
- [ ] **A.4 Rename `llm_reason` → `reason`.** No LLM writes it — it is a deterministic template
      from `reason.build_reason`. The name is now a lie. Touches `screener.py:signal_fieldnames`
      + the CSV header. Safe: the dashboard reads snapshots, and the guard that policed this
      column dies in A.1.
- [ ] **A.5 Delete `market_screener_plan.md`.** Stale — says "five signals" and assumes a weekly
      horizon. Superseded by this file. (Kills the other half of old Phase 4.)
- [ ] **A.6 Reconcile `PROJECT_MAP.md`.** Drop the Pipelines section, the pipe rows, Gotcha 1
      (dissolved), Gotcha 8 (model defaults disagree — no model left), and the tradingagents /
      ta_results rows. Add the dashboard.

**Gate:** `python screener.py --replay --no-llm=REMOVED --output f1.csv` twice → byte-identical.
Removal must not touch the determinism gate.

### Phase B — Dashboard

**Architecture:** reads snapshots, not CSVs. The CSV is truncated to `--n` (`screener.py:132` —
today's file has **12 rows**, not the 366 that passed filters). `load_snapshot()` + `score_all()`
is already pure and network-free, which is exactly what a dashboard wants — and it is the payoff
for Phase 1's determinism work.

```
market_screener/dashboard/
  app.py          # entry + run picker + tabs.  streamlit run dashboard/app.py  (cwd MUST be market_screener/)
  data.py         # @st.cache_data over load_snapshot + score_all; returns_for(ticker, window)
  tearsheet.py    # quantstats, RETURNS-fed, disk-cached per (ticker, window)
  views/table.py | ticker.py | diagnostics.py | weights.py
```

- [ ] **B.1 Cached data layer.** `score_all` is ~1.3 min (Monte Carlo, 5000 sims × 400) — cache
      per `(run_ts, config hash)`. Run picker lists `data/raw/*`.
- [ ] **B.2 Ranked table + filters.** All 366 rows. Sort/filter by sector, grade, score, coverage,
      `meme_flag`; ticker search.
- [ ] **B.3 Per-ticker detail.** Grade ladder, signal breakdown vs pool, the `reason` drivers,
      Monte Carlo distribution, news buzz.
- [ ] **B.4 quantstats tearsheet** on the detail page, window toggle over `cfg.ladder_windows`
      (3mo / 1y / **2.5y** / 5y / 10y), benchmarked vs SPY from `reference.parquet`.
      **Returns-fed, never prices.** ~1.7s / 729 KB per report, disk-cached.
      Note: the toggle uses **2.5y, not 2y** — those are the config's real ladder windows, so the
      tearsheet matches the grades shown next to it. 2y exists nowhere in the pipeline.
- [ ] **B.5 Signal diagnostics.** Per-signal sd, distinct count, fraction pinned at min/max,
      histogram. This is the view that would have caught the dead `news` constant and the 84%
      saturation without a manual measurement — `lessons.md` says to check spread before trusting
      a signal, so the tool should just show it.
- [ ] **B.6 Weight tuning.** Sliders over `cfg.weights` → live re-rank. **Must call the production
      `scorer._composite`**, not a copy — a second renormalization implementation is exactly the
      duplicate-fetcher bug from `lessons.md`. Recomputing from cached signals is cheap; no
      re-score. Show rank deltas vs the 0.45/0.35/0.10/0.10 prior.
  - [ ] **B.6a** `score_all(..., apply_filters=False)` so the dashboard filters itself. Needed
        because `coverage` is weight-dependent, so `min_coverage` re-admits/drops tickers as the
        sliders move. Keeps one filter implementation.
- [ ] **B.7 `requirements.txt`:** add `streamlit`, `quantstats` (display-only — comment it).
      Both already installed (streamlit 1.56.0, quantstats 0.0.81).

**Gate:** the dashboard's composite for the default weights must equal the CSV's
`composite_score` for the same snapshot, to 4dp. If the dashboard disagrees with the pipeline,
one of them is lying.

### Open

- [ ] Fix the `lessons.md` quantstats entry — the mechanism is wrong (see above). The *rule*
      ("verify against a hand-computed answer") is right, and the entry itself is proof: it was
      written from one observation without reading the source, and got the cause wrong while
      getting the verdict right.
- [ ] Should `screener.py` write the full scored pool and let `--n` cap only the printed table?
      The CSV being a top-N artifact is why it is useless as a dashboard source. Not blocking —
      the dashboard reads snapshots.

---

## Signal-layer overhaul — deterministic, 2-year-horizon screener

Grilled and locked 2026-07-16. Supersedes the news-only plan and the first overhaul draft.

### The decision that reframed everything

**Holding period is years, not weeks.** Every window in `config.py` was tuned for a horizon that is
not traded: `momentum_window=5`, `lookback_days=7` (news + social), `period="6mo"` price history,
`capitol_trades_pages=3` (~60d). All wrong for a 2-year hold.

**The universe is seeded entirely from short-term attention** — Yahoo day_gainers/most_actives,
StockTwits trending, Reddit hot/new, Finviz unusual-volume. Resolution: **attention is discovery,
fundamentals is selection.** Those sources keep defining the pool; they leave the composite
entirely. Weighting attention in the ranking *and* using it to build the universe counts it twice.

### Why this got big: the bug class

Every scorer maps to 0–10 via hand-picked absolute constants. Five are already stale:

| Constant | Where | Reality |
|---|---|---|
| 8 weighted articles → 10 | `news.py:48` | fossil from the `yf.Ticker().news` era (~10 items). Google News returns 100. Measured 6.5–114.5. `news` sd = **0.00** |
| `max_st_rank = 50` | `social.py:8` | trending returns **30**; last place scores 4.08 instead of ~0 |
| StockTwits 403 | `stocktwits.py` | `0.6·reddit + 0.4·0` → **capped at 6.0/10**, 3 distinct values across 20 rows. cloudscraper → HTTP 200 (verified) |
| Wikipedia 403 | `yahoo.py:46` | `fetch_wikipedia_index()` returns **0 tickers** — the last-resort pool fallback is dead. `pd.read_html(url)` with no User-Agent. The near-identical `ticker_universe.py:49` passes one and returns **501**. Fails silently (caught → warn → empty) |
| ratio < 1 → clipped 0 | `volume.py:21` | zero-inflated: **11 of 20** tie at 0.0 |
| growth saturates +50% | `fundamentals.py:36` | DELL earningsGrowth = **282%** |

**Two determinism bugs, both verified:**
- `sources/__init__.py:57` — `set(list(pool)[:400])`; string hash seeds randomize per process.
  Fingerprinted 3 runs → 3 different universes from identical inputs.
- `scorer.py:154` — sorts on score only; stable sort ⇒ ties resolve by thread completion order.

### Decisions locked

| Branch | Decision |
|---|---|
| **Horizon** | **2 years.** All windows follow from this |
| Scope | Signal-layer overhaul |
| Determinism | Ingest writes a snapshot; scoring is a pure function of it; `--replay` |
| Normalization | **Absolute** where a real zero exists (excess-vs-SPY, sentiment); **percentile** for counts; **sector-percentile** for fundamentals |
| **Peer group (price/risk)** | **Market-relative — excess sharpe vs SPY**, not pool percentile. Absolute standard, comparable across runs |
| Peer group (fundamentals) | Sector-relative percentile (pool-wide fallback if sector n<5) |
| Missing data | Score observed signals only, renormalize per ticker, emit `coverage`. Never impute 5.0 |
| Attention | **Discovery only — weight 0.00.** Seeds the pool, never ranks |
| Sentiment | Kept in composite at low weight (0.10 total); two lexicons, validated vs StockTwits labels |
| StockTwits | Revived via cloudscraper; trending → buzz (display), streams → human labels |
| quantstats | Orthogonal metrics only, long windows. Filter + score |
| Monte Carlo | **Display + filter + confidence column. NOT in the composite** |
| **Multi-window ladder** | **3mo / 1y / 2.5y / 5y / 10y**, excess-vs-SPY per window |
| **Gold metric** | **Letter grade per window → `gold_gpa` on a 4.0 scale.** GPA ranks; `gold_worst` + grade string display |
| **Grade cuts** | Per-window quantiles of a S&P500 reference universe, **recalibrated each run and written into the snapshot** |
| LLM | Out of the ranking path; reason = deterministic template |
| Weights | Category-level, split within |
| Validation | `proj_log` + forward returns + per-signal IC |

### The multi-window ladder

Purpose: separate long-term compounders from high-attention pumps. Measured, not assumed.

| Window | Answers |
|---|---|
| 3mo | is it hot right now (pump detector) |
| 1y | medium trend |
| **2.5y** | **holding-period-matched** |
| 5y | real track record |
| 10y | is it actually a compounder |

**6mo was dropped:** ρ +0.86 with 3mo — a column with no extra view. Nested windows correlate
mechanically (2.5y *is* half of 5y): adjacent ρ runs 0.62–0.86, so five windows buy ~3 independent
views, not five. Kept anyway because the *divergence* between them is the signal.

**Scored market-relative, not pool-relative.** `xs_<w> = sharpe(stock, w) − sharpe(SPY, w)`.
Pool percentile would make "gold" depend on which memes got scraped that morning; excess-vs-SPY is
an absolute standard with a real zero **and is comparable across runs** — which retires the
"percentiles aren't comparable between runs" risk. One SPY fetch, cached.

**Why `min` and not consistency.** `-|divergence|` (consistency) was tested and rejected: it cannot
see level. It ranked **MSFT #1 with a −0.66 one-year sharpe**, and ICE #8 at −0.82 — reliably
mediocre scores maximum. Measured separation of known compounders from known pumps:
consistency +7.2, worst-window +10.7, penalised-mean +10.8.

### The grade scale (4.0 GPA)

Each window gets a letter from its excess sharpe; `gold_gpa` = mean of the letters. Precedent: the
baseball repo's `quality_starts.py` grades each start and takes a GPA over starts.

```
A 4.0 | A- 3.7 | B+ 3.3 | B 3.0 | B- 2.7 | C+ 2.3 | C 2.0 | C- 1.7 | D+ 1.3 | D 1.0 | F 0.0
```

**Cuts are per-window quantiles of the reference universe, not one pooled table.** Pooled cuts were
tested and rejected: window dispersion differs wildly (3mo sd **1.63**, 5y sd **0.38**), so 90% of
5y values fall in `[−0.89, +0.11]` and the 5y window **structurally cannot award below C+** while
3mo hands out F's freely — GPA variance would be driven by the 3-month window on a 2-year tool.

**GPA ranks, not `worst`.** They rank near-identically (0.2 places apart on average, max 1), so the
tiebreak is failure modes: GPA is unbiased when windows are missing, `worst` is structurally biased
toward short-history names (min over 3 windows beats min over 4 — **UMAC ranked #8 with 2.4y of
history**), which is exactly the meme bias the ladder exists to expose. GPA's only real weakness —
`A/A/A/F` = `B/B/B/B` = 3.0 — is a *display* problem, fixed by shipping `gold_worst` alongside.
`worst`'s bias is a *ranking* problem and cannot be fixed by adding a column.
Horizon-weighted GPA was tested: ≤1 place of movement for 4 new constants. Rejected.

**Cuts are recalibrated every run and written into the snapshot.** Freezing was the original plan
and the drift data killed it — the 3mo "A" line ranged **−0.76 to +2.65** across 2019–2026 (a 3.41
sharpe spread), and the share of S&P500 names beating SPY swung **4% → 78%** (mid-2022 the index was
dragged by mega-cap tech so most stocks beat it; today the index *is* the AI winners). A stock with
a constant `xs = +0.45` grades anywhere from below-B− to A depending only on the calibration date.
Determinism is preserved because the cut table lives **in the snapshot** — replay reads the cuts it
was scored with. Provenance recorded, not assumed. Cost: one batched 150-ticker fetch per run.

Sanity check (per-window cuts, today):
```
MU    A  A  A  A   GPA 4.00  worst 4.0     DELL  A  A  A  A   GPA 4.00  worst 4.0
AAPL  A  A  A- A-  GPA 3.85  worst 3.7     IBKR  B+ B+ A  A   GPA 3.65  worst 3.3
KO    A- B+ A- A-  GPA 3.60  worst 3.3     JNJ   B- A  A  B+  GPA 3.50  worst 2.7
META  C  C  B  B   GPA 2.50  worst 2.0     SMCI  C+ D+ C  A-  GPA 2.33  worst 1.3
MRNA  B  B+ D+ D   GPA 2.15  worst 1.0     MSFT  C  D  C- B-  GPA 1.85  worst 1.0
```
Read right-to-left for the trajectory: MSFT `B- → C- → D → C` (deteriorating), SMCI `A- → C → D+ →
C+` (crashed pump), MU straight A's.

**On MSFT** (the case that drove this): excess sharpe vs SPY is **−2.42 (3mo), −2.32 (1y),
−1.05 (2.5y), −0.37 (5y)** — it has not beaten the market risk-adjusted at any horizon in five
years. Ranking it low is correct; the reputation is a 20-year artifact, which is why the 10y window
was added. The data is allowed to disagree with the prior.

**Derived, display-only:** `divergence` = pct(3mo) − pct(5y) (ρ ≤ 0.49 vs every window, so it is
genuinely orthogonal — unlike P(goal)'s ρ 0.98 with sharpe), `consistency`, and
`meme_flag` = high divergence AND high attention AND (small cap OR short history). Divergence alone
is **not** a meme detector — its top hit was **MET (MetLife)**, a large-cap insurer having a good
quarter.

### Signal taxonomy — 8 ranking signals, 4 categories

```
FUNDAMENTALS  0.45   value, quality, growth                    (3 x 0.15)
PRICE/RISK    0.35   gold_gpa              0.175
                     max_drawdown (2.5y)   0.0875
                     volatility   (2.5y)   0.0875
DIRECTION     0.10   news_sentiment, social_sentiment          (2 x 0.05)
INSIDER       0.10   capitol_hill                              (1 x 0.10)
```
**Weight 0 (discovery / display only):** `gold_worst`, `grades` (e.g. `"B-/A/A/B+"`),
`xs_3mo`…`xs_10y`, `divergence`, `consistency`, `meme_flag`, `history_years`,
`windows_available`, `news_buzz`, `social_buzz`, `rel_volume`, `p_goal_2y`, `p_bust_2y`,
`mc_confidence`, `coverage`.

- `rel_volume` leaves the composite — "unusually active today" is attention, not 2-year risk.
- Standalone `momentum_12_1` is **subsumed by the ladder** — `xs_1y` already carries it, and the
  ladder is the momentum structure. Revisit if Phase 3 IC says otherwise.
- `gold_score` and `xs_2.5y` are correlated by construction (the min includes it) — only
  `gold_score` is weighted, to avoid the double-count that killed the sharpe-aliases.

### Windows (all re-derived from the 2y horizon)

| Window | Was | Now |
|---|---|---|
| price history fetch | `period="6mo"` (126 bars) | **10y** (the ladder needs it; ~81% of the pool has it) |
| sharpe | 6mo, pool-relative | **excess vs SPY at 3mo/1y/2.5y/5y/10y** |
| max_dd / volatility | 6mo | **2.5y** (horizon-matched) |
| momentum | 5d z-scored vs 90d | dropped — subsumed by the ladder |
| capitol_hill | ~60d | **1y+** |
| news / social lookback | 7d | unchanged — feeds discovery + filters, not ranking |

---

## Phase 1 — Foundation ✅ done 2026-07-16 — see `tasks/accomplished.md`

Determinism gates all met on the real 384-ticker pool. Replay is byte-identical, scoring is pure
(verified with sockets blocked). Sector-depth risk retired: 0% of the real pool sits in a sector
below `min_peers=5`.

## Phase 2 — Signals

**Re-measured on the real 384-ticker pool (snapshot `20260716_144039`) — two premises changed:**

| Signal | Old claim (20-row sample) | Real pool (381 scored) |
|---|---|---|
| `social` | "capped at 6.0, 3 distinct values" | **sd 0.00, ONE distinct value, all 381 at 0.0 — fully dead** |
| `news` | "sd = 0.00, a constant" | sd 1.29, 13 distinct, but **321/381 (84%) pinned at 10.0** |
| `volume` | "11 of 20 (55%) at 0.0" | **278/381 (73%) at 0.0** |
| `momentum` | — | sd 1.97, 367 distinct — the healthiest signal |
| `fundamentals` | — | sd 1.38, 313 distinct — working |

- **`news` is not literally constant** — that was a 20-row artifact. It is 84% saturated, which is
  still broken and still 2.7's job, but state it accurately.
**Sources: all five are now alive (2026-07-16) — see `tasks/accomplished.md`.** Reddit's `.json`
is 403 for every client, but crawl4ai on the old.reddit HTML page works (user's call). StockTwits
via cloudscraper. Wikipedia fallback 0 → 501. `social` measured dead (sd 0.00) → working
(sd 1.32, 31 distinct). Reddit mention extraction was matching English words; fixed.
**Consequence for 2.9:** `created_utc` is now available on 100% of posts. **Consequence for 2.8:**
Reddit `selftext` is gone (listing pages carry titles only) — sentiment has titles + StockTwits
streams, not post bodies.

- [ ] **2.0 Fix the Wikipedia fallback.** `yahoo.py:46` needs the User-Agent that
      `ticker_universe.py:49` already passes. One line; the emergency pool fallback currently
      returns 0. Consider merging the two duplicate fetchers.

**Phase 2 shipped 2026-07-16 — see `tasks/accomplished.md`.** 2.1 ladder, 2.2 fundamentals x3,
2.3 risk metrics, 2.5 Monte Carlo, 2.7 news relevance, 2.9 buzz, 2.10 filters, 2.11 wire — all
done and verified on the real pool. The composite is fundamentals-led; #1 went from a $1.05
penny stock to EFC/JPM/MU-class names; no ranking signal is dead. Replay stays byte-identical.

**Deviations from the locked plan (both with measured evidence, both in accomplished.md):**
- **quantstats is not a dependency.** sharpe/volatility match numpy to 0.00e+00 and numpy is 4x
  faster; `qs.stats.max_drawdown` silently returns garbage on prices (KO -54% vs the true -17.3%).
- **`momentum` dropped, not replaced** (old item 2.4). The plan's taxonomy already said the ladder
  subsumes it; item 2.4 contradicted the taxonomy and was stale. Revisit if Phase 3 IC disagrees.

### Still open in Phase 2

- [ ] **2.6b StockTwits streams → human labels.** Trending is live, but `streams/symbol/<T>.json`
      (1 req/ticker) carries the bullish/bearish labels that 2.8's validation gate needs.
      Throttle + degrade; a 400-request burst is still unproven (12 sampled).
- [ ] **2.8b Validate the sentiment lexicon.** **v1 is shipped but never validated** — the plan's
      gate was "agreement vs StockTwits labels; DELL's -14% day scores < 4.0" and neither has
      been run. Blocked on 2.6b. Until then `news_sentiment` + `social_sentiment` are 0.10 of the
      composite resting on a guess.
- [ ] **2.8c `social_sentiment` is missing for 360/367 rows.** Only ~45 tickers get Reddit
      mentions and few titles contain lexicon words, so it renormalizes away for ~98% of the pool.
      Correct behaviour, but it means the signal is nearly inert — decide whether StockTwits
      streams (2.6b) fill it, or whether DIRECTION should be news-only at 0.10.
- [ ] **2.3b `ulcer_index`** — implemented in `metrics.py` but unused. Include only if it earns a
      slot against max_drawdown (the plan's own bar: "if it earns it").

## Phase 3 — Measurement

- [ ] **3.1 `proj_log`** — every run's ranks + per-signal scores.
- [ ] **3.2 Forward returns + IC.** Horizon-matched (the 2y horizon means real IC needs years;
      use 3/6/12-month interim reads and say so).
- [ ] **3.3 Baseline gate.** Beat equal-weight and beat SPY, or it does not ship (mirrors the
      "beat Marcel" gate in the baseball repo).
- [ ] **3.4 Fit weights** from IC once forward data exists. Until then they are an explicit guess.
- [ ] **3.5 Test the discovery premise.** Does attention-seeding beat a broad-index seed at a 2y
      horizon? Currently an untested assumption baked into the architecture.

## Phase 4 — Docs — **absorbed into the PIVOT's Phase A**

`PROJECT_MAP.md` → A.6. The "five signals" fix dissolves rather than lands: `debug_llm.py` is
deleted (A.1) and `market_screener_plan.md` is deleted (A.5), so both stale docs go away instead
of being corrected.

### Open / accepted risks

- **The 2y horizon is a bet on a pool built from 7-day attention spikes.** Coherent only under
  "attention discovers, fundamentals select". Phase 3.5 is the test.
- **Beating SPY is genuinely rare — market-wide, not a pool artifact.** Only **13% of S&P500 names**
  have positive excess sharpe (3mo 15%, 1y 13%, 2.5y 7%, 5y 17%; pooled median **−0.78**).
  `xs = 0` sits at the **87th percentile** — merely matching the market beats 87% of the index's own
  constituents, because index returns come from a minority of winners. This is why grading is
  norm-referenced against the reference universe rather than anchored at "C = matched market", and
  why `gold_gpa` must rank rather than gate.
- **10y availability drops off hard** for post-2016 listings (SPACs, recent IPOs). `windows_available`
  will do real work; expect the ladder to be 3-of-5 for much of an attention-seeded pool.
- Fundamentals percentiles remain pool/sector-relative while price/risk went market-relative — two
  different peer-group philosophies in one composite. Defensible (valuation only means anything
  within a sector) but worth revisiting if IC disagrees.
- ~~Sector-bucket depth unverified~~ — **resolved 2026-07-16.** Real 384 pool: 11 sectors,
  thinnest 9 names, 0% below `min_peers=5`.
- Lexicon v1 is a guess until 2.8's StockTwits-label measurement.
- ~~Old CSVs schema break~~ — **resolved 2026-07-16.** Fail loudly (user's call). `screener_csv.py`
  validates the header and exits nonzero; the duplicate readers in both pipes merged into it.
- **Reddit is 403 behind OAuth (new).** Discovery drops to 4 sources; `social_sentiment` loses its
  Reddit half. Decision needed before 2.6/2.8.
- 400-request StockTwits burst unproven (12 sampled).
- IC at a 2y horizon needs years of forward data. Interim reads are directional, not conclusive.
- `requirements.txt` gains quantstats (pulls matplotlib, seaborn, scipy, tabulate) + cloudscraper.
