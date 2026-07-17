import json
import re
from typing import List, Optional

import requests

from config import Config


_SYSTEM_PROMPT = """You are a professional equity analyst performing a triage pass on a pre-scored list of stock candidates.

Your job:
1. REMOVE obvious noise: pure meme spikes with no news catalyst, likely data artifacts,
   micro-cap stocks with zero news activity, and tickers showing signs of volume manipulation.
2. RE-RANK the remaining survivors by holistic conviction across all six signals
   (momentum, volume, news, social, fundamentals, capitol_hill).
3. Return EXACTLY {n} tickers.

You must respond with ONLY a JSON array — no explanation, no markdown, no extra text.
Format: [{{"ticker": "XXXX", "rank": 1, "reason": "one concise sentence"}}, ...]

Rank 1 = highest conviction. Reasons must be specific to the signals, not generic.
"""

_USER_TEMPLATE = """Here are {count} pre-scored candidates. Score each signal is 0–10.
Select and rank the best {n} tickers.

Candidates:
{candidates_json}
"""


def _build_candidates_text(candidates: List[dict]) -> str:
    rows = []
    for c in candidates:
        rows.append(
            f"{c['ticker']}: composite={c['composite_score']:.2f} | "
            f"momentum={c['momentum']:.1f} volume={c['volume']:.1f} "
            f"news={c['news']:.1f} social={c['social']:.1f} "
            f"fundamentals={c['fundamentals']:.1f} capitol_hill={c.get('capitol_hill', 5.0):.1f} | "
            f"price=${c['price_usd']:.2f}"
        )
    return "\n".join(rows)


def _parse_llm_response(text: str, n: int, candidates: List[dict]) -> List[dict]:
    # Strict parse first
    try:
        # Strip Gemma think blocks and markdown fences, then extract the JSON array
        clean = re.sub(r"<\|?think\|?>.*?</?\|?think\|?>", "", text, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"```[a-z]*\n?", "", clean).strip()
        # Find the outermost JSON array
        start = clean.find("[")
        end = clean.rfind("]")
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        parsed = json.loads(clean)
        if isinstance(parsed, list) and len(parsed) > 0:
            # Validate structure
            valid = [
                item for item in parsed
                if isinstance(item, dict) and "ticker" in item and "rank" in item
            ]
            if valid:
                return sorted(valid, key=lambda x: x.get("rank", 999))[:n]
    except (json.JSONDecodeError, ValueError):
        pass

    # Lenient fallback: extract tickers mentioned in order
    print("[WARN] LLM returned malformed JSON — falling back to composite-score ordering")
    ticker_pattern = re.compile(r'\b([A-Z]{1,5})\b')
    seen = set()
    ordered = []
    candidate_set = {c["ticker"] for c in candidates}
    for m in ticker_pattern.finditer(text.upper()):
        t = m.group(1)
        if t in candidate_set and t not in seen:
            seen.add(t)
            ordered.append(t)

    # Build result from extracted tickers, pad with composite-score order if needed
    result_tickers = ordered[:n]
    if len(result_tickers) < n:
        for c in candidates:
            if c["ticker"] not in result_tickers and len(result_tickers) < n:
                result_tickers.append(c["ticker"])

    ticker_to_cand = {c["ticker"]: c for c in candidates}
    return [
        {
            "ticker": t,
            "rank": i + 1,
            "reason": "Composite score ranking (LLM output malformed)",
        }
        for i, t in enumerate(result_tickers)
        if t in ticker_to_cand
    ]


def llm_rank(candidates: List[dict], cfg: Config) -> List[dict]:
    n = cfg.n_results
    system = _SYSTEM_PROMPT.format(n=n)
    user = _USER_TEMPLATE.format(
        count=len(candidates),
        n=n,
        candidates_json=_build_candidates_text(candidates),
    )

    try:
        resp = requests.post(
            f"{cfg.ollama_base_url}/api/chat",
            json={
                "model": cfg.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192},
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        if not text:
            raise ValueError("Empty response from Ollama")
        return _parse_llm_response(text, n, candidates)

    except Exception as e:
        print(f"[WARN] LLM cull pass failed: {e} — falling back to composite-score ordering")
        return _composite_fallback(candidates, n)


def _composite_fallback(candidates: List[dict], n: int) -> List[dict]:
    top = candidates[:n]
    return [
        {
            "ticker": c["ticker"],
            "rank": i + 1,
            "reason": "Composite score ranking (LLM unavailable)",
        }
        for i, c in enumerate(top)
    ]
