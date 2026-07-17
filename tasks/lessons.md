# Lessons

Past mistakes and the rules that prevent them.

## A constant calibrated for one data source is a fossil the moment the source changes

**What happened.** `scoring/news.py` saturated at 8 weighted articles → score 10. That threshold was
correct when the scorer read `yf.Ticker(x).news`, which returns ~10 items. The source was later
swapped to Google News RSS, which returns 100. The threshold never moved, so every ticker scored
10.0 and `news` contributed a constant +2.0 to every composite — sd = 0.00 across a 20-row run.
The `providerPublishTime` key left behind in the RSS adapter is the fingerprint of the old source.

**Why it survived.** Nothing measured signal variance, and the LLM downstream narrated the constant
back as if it were evidence ("excellent news catalyst") — which read like the signal was working.

**Rule.** When changing a fetcher, re-derive every constant downstream of it in the same session.
Prefer cross-sectional percentile over absolute thresholds — a percentile has no constant to go
stale. Related fossils found the same day: `max_st_rank=50` (trending returns 30), growth
saturating at +50% (DELL: 282%), volume clipping ratio<1 → 0 (11 of 20 tickers tied at 0.0).

## The same fix must be applied to every copy of a fetcher

**What happened.** `sources/ticker_universe.py:49` calls `pd.read_html(url,
storage_options={"User-Agent": "Mozilla/5.0"})` and returns 501 tickers. `sources/yahoo.py:46`
calls `pd.read_html(url)` on the *same Wikipedia pages* with no User-Agent, gets **403**, and
returns **0**. That function is `fetch_wikipedia_index` — the last-resort pool fallback that fires
when every primary source fails. The emergency parachute has been packed inside-out, silently.

**Rule.** When two functions fetch the same resource, they are one function. If a header, retry or
cache fix is needed in one, it is needed in the other — or merge them. Same class as the StockTwits
403: a User-Agent, silently swallowed.

## A constant calibrated today encodes today's regime

**What happened.** Grade cut points derived from the cross-section of excess-sharpe-vs-SPY move
enormously with the market regime. The 3-month "A" line (p90) ranged from **−0.76 to +2.65** across
2019–2026, and the share of S&P500 names beating SPY swung **4% → 78%** — in mid-2022 the index was
dragged down by mega-cap tech so most stocks beat it; today the index *is* those winners. A stock
with a constant `xs = +0.45` grades anywhere from below-B− to A depending purely on when the table
was frozen.

**Rule.** Freezing a calibration for reproducibility is the wrong lever — it buys determinism by
encoding a regime that will rot. Recalibrate, and put the calibration **in the snapshot** so the
replay is still exact. Determinism should come from recording inputs, not from refusing to update
constants.

## A signal with no variance is dead, not neutral

**What happened.** `news` was constant at 10.0 and `social` was structurally capped at 6.0 (its
StockTwits half returned 403, so `0.6·reddit + 0.4·0` can never exceed 6). Both looked like
working signals in the output — plausible numbers in a plausible range.

**Rule.** Before trusting any signal, check its spread across a real run: `sd`, distinct value
count, and fraction pinned at the min/max. `social` had **three** distinct values across 20 rows.
A signal that is constant contributes nothing but weight.

## "Neutral 5.0" must not mean "no data"

**What happened.** Every scorer returns 5.0 on missing data. `capitol_hill` was 5.0 for 8 of 20
rows — indistinguishable from a genuinely average ticker. Silent exception handling in the fetchers
means a dead source looks like a neutral market.

**Rule.** Score only observed signals and renormalize weights per ticker; emit a `coverage` column.
Reserve 5.0 for "measured, and average".

## Don't let an LLM narrate numbers it cannot verify

**What happened.** The ranker sees only six numbers per ticker — no headlines, no company name, no
market cap — yet its prompt asks it to remove "meme spikes with no news catalyst" and "micro-caps".
It cannot see any of that. On 2026-05-15 it ranked DELL #4 with "high news coverage... indicating
institutional interest" on a day whose actual headlines were "shares tumble 14%" and "plunging".

**Rule.** Never ask a model to judge what is not in its context. If the ranking is deterministic,
build the reason from the real drivers instead — it cannot hallucinate and it costs nothing.

## Verify tool output actually came from a tool

**What happened.** The TradingAgents pass with a local Ollama model wrote a tool call *and invented
its output* — a CSV of AMD at $150–162 when AMD was $432. No `AMD-YFin-*` file existed in
`data_cache`, proving the fetch never ran. `fundamentals_report` has been 0 characters across all
46 saved runs.

**Rule.** When an agent framework claims to have fetched data, verify the side effect (a cache file,
a request log) — not the prose. Prose is free to invent.

## The wall clock is an input — snapshot it like any other

**What happened.** Splitting ingest from scoring was supposed to make scoring a pure function of
the snapshot. Two things still leaked the clock in: `score_news` computed its 7-day cutoff from
`time.time()` **at score time**, so replaying yesterday's snapshot today scored every article as
stale; and `_score_ticker` called `is_market_open()` per thread, so whether the partial bar got
dropped depended on what time of day you replayed. Both would have silently produced *plausible*
different numbers from identical data — the same failure mode as every other bug in this repo.

**Rule.** "Pure function of the snapshot" means *the snapshot*, and `now` is not in it unless you
put it there. Record `ingest_time` and pass it to anything time-relative. When you claim purity,
prove it — block sockets and re-score, don't just eyeball it. A third leak (a network finviz P/E
call inside `score_fundamentals`) was only found by doing exactly that.

## A dead source and a degraded source look identical from the output

**What happened.** `social` was documented as "capped at 6.0 because StockTwits 403s, so
`0.6·reddit + 0.4·0`". On the real 384-ticker pool it is **0.00 for all 381 scored tickers** —
because Reddit's public `.json` now 403s too, for every User-Agent, and unlike StockTwits
cloudscraper does not fix it. The documented diagnosis was written from a 20-row CSV and had the
mechanism right but the magnitude wrong. Separately, `news` was recorded as "sd = 0.00, a
constant"; on 384 rows it is sd 1.29 with 84% pinned at max — broken, but not the way it was
written down.

**Rule.** Measure signal health on the real pool, not on a saved 20-row output. Small samples
turn "84% saturated" into "constant" and hide a source that died after the sample was taken.
And when a source degrades, re-check its *siblings* — 403 arrived at StockTwits, Wikipedia, and
Reddit separately, and each was swallowed silently.

## Normalising before matching destroys the thing you were matching on

**What happened.** `reddit.py:_extract_tickers` did `text_upper = text.upper()` and *then* ran an
all-caps regex `\b([A-Z]{2,5})\b` over the result — so every 2-5 letter word in a post title
became a ticker candidate. The only filters left were a 7,070-symbol whitelist and a 29-word
noise list, and `ON`, `OR`, `YOU`, `IT`, `UP`, `NOW`, `BE` are all real tickers. "Doubled down
**on** $NFLX **now**, **it** is **up**" scored four bogus mentions. Measured on 150 live posts:
**48 tickers extracted, of which the top 8 were English words**; fixing the case sensitivity cut
it to 17, essentially all real names.

**Why it survived.** Reddit's API had been returning 403 for long enough that `reddit_counts` was
always empty, so the bug had no output to be visible in. Reviving the source is what exposed it —
a dead upstream hides every bug downstream of it.

**Rule.** Case-fold for comparison, never for detection: if capitalisation *is* the signal,
matching against the normalised copy throws the signal away. More generally, when you revive a
dead source, re-validate everything downstream of it — those code paths have never actually run
on data.

## Two dict keys with one name: the row disagreed with its own score

**What happened.** `_score_ticker` built its output row by spreading the ranking signals and then
the display columns: `{**signals, **gold}`. Both defined `gold_gpa` — the signal was the 0–10
value the composite was computed from, the display was the 0–4 report card. The later spread won,
so the emitted row carried a number the score was *not* derived from. Every reason string then
read "weak vs-SPY record 2.9" for a signal the composite had scored 7.25.

**Why it nearly survived.** Both numbers were plausible and on plausible scales, and the ranking
was still correct — only the explanation and the CSV column were wrong. It surfaced only because
the generated reason contradicted the grade string next to it.

**Rule.** A value that is displayed and a value that is scored must not share a key. Name them
apart (`gold_score` vs `gold_gpa`) and assert the sets are disjoint at construction — a silent
overwrite between two dicts is invisible in review and produces output that is internally
inconsistent rather than merely wrong.

## Verify the library before you take the dependency

**What happened.** The plan locked "use quantstats" for sharpe / max_drawdown / volatility.
Checking first: `sharpe` and `volatility` matched a five-line numpy version to **0.00e+00** and
the numpy version was **4x faster**. But `qs.stats.max_drawdown` **treats its input as returns**,
so passing it prices makes it compound prices — KO's 5-year drawdown came back **−54%** when the
real answer is **−17.3%** (58.43 → 48.33, Oct 2023, confirmed by hand). It does not raise; it
returns a believable wrong number. The library's one distinctive feature, `montecarlo`, had
already been rejected as unusable.

**Rule.** A dependency has to earn its weight against the code it replaces. Four one-line
formulas did not justify matplotlib + seaborn + scipy + tabulate. And when a library takes an
ambiguous argument (prices vs returns), verify against a hand-computed answer before trusting it
— "it ran and gave a number" is not verification.

## Reproducibility is a precondition for tuning, not a nice-to-have

**What happened.** `_score_ticker` fetches and scores in the same thread, so you cannot re-score
without re-fetching a changed internet — no A/B of two lexicons is possible. Separately,
`pool = set(list(pool)[:400])` truncates a set, and Python randomizes string hash seeds per
process: three runs, three different universes from identical inputs.

**Rule.** Never slice an unordered collection. Split ingest from scoring and snapshot the inputs
before tuning anything that consumes them.
