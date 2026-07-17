# TODO

## Tracking tab — "which metric leads to the best returns"

Grilled and locked 2026-07-17. A new dashboard tab that turns the date-stamped CSVs into a
paper-trading experiment: each screening run buys the top picks per metric, and we track their
forward returns over time to see which signal actually predicts gains.

**SHIPPED 2026-07-17 — see `tasks/accomplished.md`.** All of T.1–T.7 done: `tracking/` back-end
(cohorts/prices/returns) + `dashboard/views/tracking.py` + 5th tab wired. `AppTest` 0 exceptions,
live P/L hand-verified (EFC −$15.48). The locked design is archived below.

**Open follow-ups (non-blocking, revisit as data accumulates):**
- [ ] Only one CSV on disk today → horizons all empty. Re-check the leaderboard once cohorts reach
      1mo/3mo so the fixed-horizon ranking actually populates.
- [ ] `tracking_position_usd` remainder cash is ignored (a $600 stock deploys $600, not $1000). Fine
      for % comparison; revisit only if a dollar-accurate book is wanted.
- [ ] Live view mixes CSV raw entry price with yfinance adjusted current close — tiny over short
      horizons, but if it ever matters, anchor live entry to the yf adjusted close too.

<details><summary>locked design (archived)</summary>

### Decisions locked (grill 2026-07-17)

| Branch | Decision |
|---|---|
| **Model** | **Cohort buy-and-hold.** Each CSV = a frozen batch of picks bought at that run's price, held forever, never sold. A metric's score = avg forward return across all its cohorts. No exit logic. |
| **Buckets (10)** | `composite` → top **10**; `value, quality, growth, gold_score, max_drawdown, volatility, news_sentiment, social_sentiment, capitol_hill` → top **3** each. |
| **Bucket direction** | Always highest normalized score. For `max_drawdown`/`volatility` (0–10, higher=less risk) that means the calmest names. |
| **Cohort frequency** | **One per CSV file** (user's call; intraday duplicates accepted). |
| **Ledger storage** | **Derived, not persisted.** Scan `outputs_TA/**/screener_*.csv`, rebuild every cohort from rows. Only cache is a prices lookup. Fully reproducible; backfills history. |
| **Entry price** | The `price_usd` already in the CSV (frozen, deterministic). |
| **Current/historical prices** | **yfinance**, cached to `tracking/price_cache/` keyed by ticker+date. Refetch only missing/newest. Tab is online-only by nature; screener determinism untouched. |
| **Position size** | `floor(1000 / price)` whole shares. If price > $1000 (floor 0), **buy 1 share**. |
| **Aggregation** | **Equal-weight avg % return** per bucket (a $1500 and a $20 name count equally). $ P/L shown too, but ranking uses avg %. |
| **Comparison basis** | **Both** — a live mark-to-market "standings" view AND a fixed-horizon analysis. **Ranking uses fixed-horizon** (apples-to-apples across cohort ages). |
| **Horizons** | **1mo / 3mo / 6mo / 1yr** (21/63/126/252 trading days). Cohorts too young for a horizon are excluded from it. |
| **Benchmark** | **SPY.** Show return AND excess-vs-SPY over the same window. |
| **Deep-dive engine** | **Reuse `dashboard/tearsheet.py`.** Each bucket → a synthetic daily return series → the existing quantstats path (equity/drawdown/monthly-heatmap/Sharpe, SPY-benchmarked). |
| **Comparison chart** | Multi-line equity curve, **SPY + top 3–4 buckets by default**, toggle any bucket on/off. |
| **Layout** | Leaderboard (top) + comparison equity curve (mid) + per-bucket drill-down w/ full quantstats tearsheet (bottom). Mirrors the Rankings table→tearsheet pattern. |

### The synthetic-strategy trick (why quantstats reuse is nearly free)

A bucket's **daily return** on any day = equal-weight avg of the daily returns of every position
currently open in it (positions switch on as cohorts are added over time). That single return
series feeds the existing tearsheet machinery unchanged. **CRITICAL — feed quantstats RETURNS, not
PRICES** (`lessons.md`: the phantom-baseline bug makes `max_drawdown(prices)` wrong for 44% of
names). The whole tracker is built on returns, so we stay on the right side of that.

### Plan

- [ ] **T.1 `tracking/cohorts.py`** — scan `outputs_TA/**/screener_*.csv`; for each CSV build the 10
      buckets (top-N per metric, entry `price_usd`, `floor(1000/price)` shares min 1). Pure, no network.
- [ ] **T.2 `tracking/prices.py`** — yfinance daily-close fetch + disk cache (`tracking/price_cache/`),
      keyed by ticker+date. `SPY` fetched once. Returns a per-ticker daily-close series aligned to
      trading days.
- [ ] **T.3 `tracking/returns.py`** — per-position forward returns; per-bucket **synthetic daily
      return series** (equal-weight of open positions); fixed-horizon aggregates (1/3/6/12-mo) across
      eligible cohorts; live mark-to-market P/L; excess-vs-SPY.
- [ ] **T.4 `dashboard/views/tracking.py`** — leaderboard table (ranked by fixed-horizon excess),
      toggleable multi-line equity curve (SPY + top buckets default), per-bucket drill-down →
      `render_tearsheet` on the synthetic series + its cohorts/picks table.
- [ ] **T.5 Wire the tab** into `dashboard/app.py` (`st.tabs`).
- [ ] **T.6 Verify** end-to-end on the real CSVs on disk; confirm a hand-computed position return
      matches; confirm the synthetic series fed to quantstats is RETURNS (0 price-fed calls).
- [ ] **T.7** Update `PROJECT_MAP.md` (new `tracking/` module block) in the same commit.

### Open / accepted risks

- Only **one CSV exists on disk today** (`2026-07-16`). The tab is real but has ~nothing to plot
  until more runs accumulate — build against it, expect sparse early views.
- CSV holds only the top `--n` (default 50); buckets are drawn from those, not the full pool. Fine —
  the picks are what a user would actually have acted on.
- Weekend/holiday entry: entry price stays the CSV `price_usd`; the return series starts at the next
  trading day's close. Decide in T.3.
- Delisted / no-yfinance-data ticker → position marked N/A, excluded from averages, flagged in UI.
- Missing metric value → ticker simply absent from that bucket (never impute).

</details>

## PIVOT — drop the LLM pipes, build a Streamlit dashboard

Decided 2026-07-17. The two second-pass pipes are cut: too slow, and TradingAgents' Ollama runs
**fabricate tool output** (`lessons.md` — AMD at $150-162 when AMD was $432; `fundamentals_report`
0 characters across all 46 saved runs). That is a correctness failure, not a speed one. Nothing
downstream of the screener survives. Ollama leaves the project entirely — the LLM already left the
ranking path last session.

This absorbs Phase 4 (docs) and dissolves Gotcha 1 (the screener writes `outputs_TA/`, the pipes
read `output/`) — with no pipes, there is no second reader to disagree with.

**Phase A shipped 2026-07-17 — see `tasks/accomplished.md`.** Pipes, orphans, LLM config and
~10 MB of outputs deleted; `llm_reason` → `reason`; `PROJECT_MAP.md` reconciled; repo now under
git. Determinism gate held (byte-identical replay, #1 still EFC 7.8847).

**quantstats verdict (measured, snapshot `20260716_164333`, 373 tickers):** the library is **not**
broken — it was called wrong. `max_drawdown(prices)` is wrong for **165/373 (44%)**, max error
**78.5%**, because it prepends a phantom baseline (`first_price > 10` → 100.0) that joins the
running peak. `max_drawdown(returns)` is **exact: 0/373 wrong**. Full mechanism in
`accomplished.md` + `lessons.md`.

**The rule Phase B depends on: feed quantstats RETURNS, never PRICES.** `metrics.py` stays the
scoring path regardless (numpy is 4x faster and exact); quantstats is display-only and ranks
nothing.

### Phase B — Dashboard  ✅ **DONE 2026-07-17 — see `tasks/accomplished.md`**

All eight modules wired and the app runs end to end: `streamlit run dashboard/app.py` renders
4 tabs, 0 exceptions, 6 dataframes, metrics populate. `app.py` + both `__init__.py` written,
`requirements.txt` updated (streamlit, quantstats). Verified with Streamlit's `AppTest` (runs the
full script incl. all tabs, quantstats tearsheet, live rescore). Only open item is a deprecation:
`ticker.py` uses `st.components.v1.html` (removal targeted post-2026-06-01) — still works on 1.56.

<details><summary>original Phase B plan (archived)</summary>

**STATE AS OF 2026-07-17 handoff:** six modules are written, `app.py` and the two `__init__.py`
files are **not**, and **not one line of the dashboard has ever been executed.** Every "done"
below means "code exists", not "works". Assume nothing renders until `app.py` exists and
`streamlit run` succeeds. The two production refactors it depends on (B.6a, `simulate_terminal`)
*are* verified — the determinism gate held after both (16,095 bytes, EFC 7.8847).

**Architecture:** reads snapshots, not CSVs. The CSV is truncated to `--n` (`screener.py:132` —
today's file has **50 rows**, not the 366 that passed filters). `load_snapshot()` + `score_all()`
is already pure and network-free, which is exactly what a dashboard wants — and it is the payoff
for Phase 1's determinism work.

```
market_screener/dashboard/
  app.py          # entry + run picker + tabs.  streamlit run dashboard/app.py  (cwd MUST be market_screener/)
  data.py         # @st.cache_data over load_snapshot + score_all; returns_for(ticker, window)
  tearsheet.py    # quantstats, RETURNS-fed, disk-cached per (ticker, window)
  views/table.py | ticker.py | diagnostics.py | weights.py
```

- [x] **B.6a** `score_all(..., apply_filters=False)` + `scorer.composite` / `filter_reasons` /
      `passes_filters` made public. **VERIFIED** — gate held, byte-identical, EFC 7.8847.
      `filter_reasons` was added beyond plan: it names every gate a row fails, so the dashboard
      can say *why* a ticker was dropped, and `passes_filters` is just its emptiness (one
      implementation).
- [x] **`simulate_terminal`** split out of `monte_carlo.simulate` so the dashboard plots the
      *actual* bootstrap distribution (same seed, same draws) rather than re-rolling its own.
      **VERIFIED** — gate held after the split.
- [x] ~~code written~~ **B.1 data layer** (`dashboard/data.py`) — `cache_resource` for the
      snapshot (46 MB of DataFrames; pickling per call would cost more than the load),
      `cache_data` for scoring keyed on `(run_ts, cfg_fingerprint)` so editing `config.py`
      invalidates. **Unrun.**
- [x] ~~code written~~ **B.2 Rankings** (`views/table.py`) — full pool, sector/search/score/
      coverage/meme filters, CSV export, dropped-rows expander with reasons. **Unrun.**
- [x] ~~code written~~ **B.3 Ticker detail** (`views/ticker.py`) — ladder, signal breakdown vs
      pool percentile, MC distribution, reason. **Unrun.**
- [x] ~~code written~~ **B.4 Tearsheet** (`dashboard/tearsheet.py`) — returns-fed, window toggle
      over `cfg.ladder_windows`, SPY-benchmarked, `verify_against_metrics` surfaces the
      qs-vs-`metrics.py` agreement **in the UI** rather than hiding it in a test. **Unrun.**
- [x] ~~code written~~ **B.5 Diagnostics** (`views/diagnostics.py`) — sd / distinct /
      fraction-pinned / missing per signal + a `health` verdict, coverage histogram. **Unrun.**
- [x] ~~code written~~ **B.6 Weight tuning** (`views/weights.py`) — sliders → `data.rescore` →
      production `scorer.composite`. Renormalizes to 1.0 (coverage is a *fraction of total
      weight*, so unnormalized sliders would inflate it past `min_coverage`). **Unrun.**

**Remaining to finish Phase B:**
- [ ] **B.8 `dashboard/app.py`** — entry, snapshot run picker, `st.tabs`, `st.set_page_config`.
      **Nothing works without this.**
- [ ] **B.9 `dashboard/__init__.py` + `dashboard/views/__init__.py`** — the views import
      `from dashboard import data`, which needs the package to be importable with
      `market_screener/` as cwd.
- [ ] **B.10 `requirements.txt`:** add `streamlit`, `quantstats` (**comment it as display-only**).
      Both already installed (streamlit 1.56.0, quantstats 0.0.81) — so a missing line here fails
      only on a fresh machine, which is the worst time to find it.
- [ ] **B.11 RUN IT.** `streamlit run dashboard/app.py` from `market_screener/`. Nothing above is
      real until this renders. Expect import errors, Streamlit API drift (1.56), and the
      `to_frame` → `st.dataframe` Arrow conversion choking on `None`-typed columns.

**Gate:** the dashboard's composite for the default weights must equal the CSV's
`composite_score` for the same snapshot, to 4dp. If the dashboard disagrees with the pipeline,
one of them is lying.

</details>

**Still open after Phase B:**
- [ ] Replace `st.components.v1.html` in `dashboard/views/ticker.py` with the non-deprecated API
      (Streamlit flags removal post-2026-06-01; `st.iframe`/`st.html` take a URL/sanitized HTML,
      not a scrollable srcdoc, so this needs a real look, not a rename). Non-blocking — works today.
- [ ] Gate not yet run: dashboard composite == CSV `composite_score` to 4dp for the same snapshot.
      Cheap to confirm and worth doing before trusting the numbers on screen.

### Open

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

- [x] **2.6b/2.8b/2.8c RESOLVED 2026-07-17 — see `tasks/accomplished.md`.** `social_sentiment` now
      comes from StockTwits `streams/symbol/<T>.json` Bull/Bear labels (schema v4), not the
      Reddit-title lexicon. Coverage **6/396 → 186/396 (47%)**; budget-capped at
      `stocktwits_stream_budget=200`. The label IS the signal, so there's no lexicon left to
      validate — 2.8b dissolves. Reddit stays discovery/buzz only.
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
