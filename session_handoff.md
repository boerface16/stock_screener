# Session Handoff — Dashboard finished + running, StockTwits social sentiment, tearsheet corruption fixed

## Where it started
Picked up from a prior handoff where the Streamlit dashboard was written but never executed. This
session: finish and run the dashboard, add an in-app "run the screener for today" button, add three
UX changes (click-a-row → tearsheet, ticker name in report, ticker search), and investigate why
`social_sentiment` was missing for ~98% of the pool. Then fixed a user-reported "corrupt" tearsheet.

## Decisions locked + what shipped
- **Dashboard shipped and runs.** `app.py` + `runner.py` + both `__init__.py` written; entry is
  `streamlit run market_screener/dashboard/app.py` **from anywhere** — `app.py` does
  `sys.path.insert(0, _ROOT)` AND `os.chdir(_ROOT)` so imports and relative `data/raw` resolve
  regardless of launch cwd. Lives in `A:\Stonks\Screener_Tool\market_screener\dashboard\`.
- **"Run screener for today" button.** `dashboard/runner.py` launches `screener.py --ingest-only`
  as a subprocess (stdout→file, polled every 2s), off Streamlit's script thread; `finalize()` snaps
  the run picker to the new snapshot. Verified: produced a real snapshot end to end.
- **`social_sentiment` re-sourced from StockTwits stream Bull/Bear labels** (was Reddit titles,
  1.5% coverage). Now **186/396 = 47%**. Required snapshot **SCHEMA_VERSION 3→4** (`st_sentiment` in
  `stocktwits.json`). Reddit-title lexicon path deleted; Reddit → buzz only. Resolves 2.6b/2.8b/2.8c.
- **3 UX changes.** Rankings table single-row selectable → tearsheet renders underneath;
  `strategy_title=ticker` so the report labels the ticker not "Strategy"; type-to-search box in
  Ticker detail. Shared `tearsheet.render_tearsheet` used by both call sites.
- **Tearsheet "corruption" fixed.** Root cause: `qs.reports.html` default `figfmt="svg"` inlines 14
  SVGs sharing ~124 element IDs + ~1300 `<use href="#id">` refs → later plots resolve to the first
  plot's clip-paths/glyphs → garbled. Fix: `figfmt="png"` in `dashboard/tearsheet.py:build_html`.

## Key files for next session
- `A:\Stonks\Screener_Tool\tasks\todo.md` — current open work; Phase B marked done, 2.6b/2.8b/2.8c
  resolved. Read first.
- `A:\Stonks\Screener_Tool\tasks\accomplished.md` — three new blocks this session (social+UX,
  run-for-today, dashboard-shipped) with metrics.
- `A:\Stonks\Screener_Tool\tasks\lessons.md` — 2 new lessons: multi-SVG ID collision; verify from a
  realistic cwd.
- `A:\Stonks\Screener_Tool\market_screener\dashboard\app.py` — entry point + ingest wiring.
- `A:\Stonks\Screener_Tool\market_screener\dashboard\runner.py` — subprocess ingest control.
- `A:\Stonks\Screener_Tool\market_screener\dashboard\tearsheet.py` — `render_tearsheet`, `figfmt=png`.
- `A:\Stonks\Screener_Tool\market_screener\sources\stocktwits.py` — `fetch_stocktwits_sentiment`.
- Plan file: none — `tasks/todo.md` drove the session (plan was written there, now marked done).
- Memory files touched: none.
- PROJECT_MAP.md: **updated** — dashboard/ module table (all rows → shipped, added `runner.py`),
  `snapshot.py` row (schema v4), `stocktwits.py` row (streams), social-coverage known-bug row,
  Gotcha 11 (figfmt=png) added.

## Running state
- Background processes: none. (Three background shells were used this session — two `--ingest-only`
  ingests `b2hkfttot`/`bq1ixw3dp` and one Streamlit `bisp93wf2` — all completed/terminated; nothing
  live.)
- Dev servers / ports: none — no Streamlit server currently running.
- Open worktrees / branches: git repo, default branch. Working tree has **uncommitted** changes from
  this session (dashboard/, scoring/, sources/, ingest.py, snapshot.py, config.py, PROJECT_MAP.md,
  tasks/). Nothing committed this session.
- Snapshots on disk: v4 `market_screener\data\raw\20260717_135916` is current. Older v3 snapshots
  (`20260716_*`, `20260717_122109`) are unreadable now and hidden from the picker.

## Verification — how to confirm things still work
- `cd A:\Stonks\Screener_Tool\market_screener && python -m streamlit run dashboard/app.py` — loads
  the v4 snapshot, 4 tabs, 0 errors. (Bash PATH lacks `streamlit`; use `python -m streamlit`.)
- `cd A:\Stonks\Screener_Tool\market_screener && python screener.py --replay 20260717_135916 --output f1.csv` twice → **byte-identical, 16,145 bytes** (determinism gate; the old 16,095/EFC-7.8847 baseline is retired — social coverage moved the composite).
- `social_sentiment` coverage: load `20260717_135916`, `score_all(..., apply_filters=False)`, count
  non-None `social_sentiment` → **186/396**.
- Tearsheet render: `build_html` output must have **0 `<svg>`, 0 duplicate ids, 14 `data:image/png`**.

## Deferred + open questions
- Deferred: `st.components.v1.html` in `views/ticker.py`/`tearsheet.py` is deprecated (Streamlit 1.56,
  removal targeted post-2026-06-01) — still works; replacement needs a real look (URL/sanitized HTML
  vs scrollable srcdoc), not a rename.
- Deferred: the 4dp gate (dashboard composite == CSV `composite_score` for the same snapshot) has not
  been run.
- Deferred: `requirements.txt` should note StockTwits streams are rate-limited (~200/hr); no cap
  documented there.
- Open: `stocktwits_stream_budget=200` caps social coverage at the top-200 pool tickers — raise it
  (accepting rate-limit risk / a slower ingest) or leave it? User has not decided.
- Open: nothing committed all session — decide whether to commit before more work.

## Pick up here
Reload the dashboard and confirm the BMO 1y tearsheet now renders cleanly (the `figfmt="png"` fix);
if the user is satisfied, the likely next action is committing the session's work or running the 4dp
composite-vs-CSV gate.
