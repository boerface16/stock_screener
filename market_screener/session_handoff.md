# Session Handoff — LLM ranker debugging and fix (Gemma4 context window)

## Where it started
The screener was running end-to-end with `--no-llm` successfully after previous session fixes. This session focused entirely on getting the LLM cull pass (`llm/ranker.py`) working with Gemma4 via Ollama. All 6 scoring signals were functional; the LLM pass was the only broken piece.

## Decisions locked + what shipped
- **Escaped curly braces in `_SYSTEM_PROMPT`** — `{"ticker": ...}` in the format string was causing `KeyError` when `.format(n=n)` was called. Fixed by doubling the braces to `{{"ticker": ...}}`. Lives in `A:\Stonks\Screener_Tool\market_screener\llm\ranker.py` line 20.
- **Removed `<|think|>` token from system prompt** — Was leaking Gemma's internal token into prompt text. Removed from `_SYSTEM_PROMPT` header.
- **Parser now strips think blocks + extracts JSON array** — `_parse_llm_response` uses regex to strip `<think>...</think>` blocks, then `find("[")` / `rfind("]")` to extract the JSON array regardless of surrounding text. `llm/ranker.py:50-56`.
- **Validation check fixed** — Changed `if len(valid) >= n` to `if valid` so a partial response (fewer than n items) is still accepted rather than silently falling through to the malformed-JSON path. `llm/ranker.py:64`.
- **Ollama `num_ctx` set to 8192** — Root cause of all failures: Ollama default context is 2048 tokens. The 40-candidate prompt uses ~2042 tokens just for system+user template, leaving no room for the candidate list. Model was responding "Please provide the list" because it never received the data. Fixed by passing `"num_ctx": 8192` in the Ollama options. `llm/ranker.py:119`.
- **`debug_llm.py` created** — Standalone script to test the LLM directly with a small synthetic candidate set. Useful for future debugging. `A:\Stonks\Screener_Tool\market_screener\debug_llm.py`.

## Key files for next session
- `A:\Stonks\Screener_Tool\market_screener\llm\ranker.py` — The file fixed this session; read this first to understand current LLM state.
- `A:\Stonks\Screener_Tool\market_screener\config.py` — `llm_candidate_multiplier` controls how many candidates go to the LLM (currently `n * multiplier = 40`). If context issues recur, this is the lever.
- `A:\Stonks\Screener_Tool\market_screener\debug_llm.py` — Quick LLM diagnostic without running the full screener.
- Plan file: `C:\Users\Jake\.claude\plans\fluttering-wondering-pelican.md` (reflects completed LLM fix plan)
- Memory: `C:\Users\Jake\.claude\projects\A--Stonks-Screener-Tool\memory\project_screener_decisions.md`

## Running state
- Background processes: none
- Dev servers / ports: none
- Open worktrees / branches: none (project has no git repo)

## Verification — how to confirm things still work
- `cd A:\Stonks\Screener_Tool\market_screener && python screener.py --n 20` — should complete with LLM cull pass producing 20 ranked tickers with signal-specific reasons (not "Composite score ranking (LLM output malformed)")
- `python debug_llm.py` — should return `[OK] Parsed successfully: 5 items` with NVDA ranked #1

## Deferred + open questions
- Deferred: StockTwits integration — API returns 403 (auth required). User has login/password and mentioned getting an API token but it was never implemented.
- Deferred: Capitol Trades `capitol_hill` score is 5.0 (neutral) for most tickers — the LLM prompt still references "five signals" in the system prompt but there are now six (capitol_hill was added). Minor inconsistency in the prompt copy.
- Open: No questions pending from user.

## Pick up here
StockTwits 403 fix is the clearest remaining open item — user has credentials and wants trending data; implement OAuth token auth or bearer token in `sources/stocktwits.py`.
