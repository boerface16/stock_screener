#!/usr/bin/env python3
"""
Debug the Ollama LLM response to see exactly what Gemma4 returns.
Usage: python debug_llm.py
"""
import sys
import json
import re
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:latest"

SYSTEM = """You are a professional equity analyst performing a triage pass on a pre-scored list of stock candidates.

Your job:
1. REMOVE obvious noise: pure meme spikes with no news catalyst, likely data artifacts,
   micro-cap stocks with zero news activity, and tickers showing signs of volume manipulation.
2. RE-RANK the remaining survivors by holistic conviction across all five signals
   (momentum, volume, news, social, fundamentals).
3. Return EXACTLY 5 tickers.

You must respond with ONLY a JSON array — no explanation, no markdown, no extra text.
Format: [{"ticker": "XXXX", "rank": 1, "reason": "one concise sentence"}, ...]

Rank 1 = highest conviction. Reasons must be specific to the signals, not generic.
"""

USER = """Here are 8 pre-scored candidates. Each signal is 0-10.
Select and rank the best 5 tickers.

Candidates:
TSLA: composite=6.67 | momentum=10.0 volume=0.5 news=10.0 social=6.0 fundamentals=4.3 | price=$445.00
AMD: composite=6.94 | momentum=10.0 volume=0.0 news=10.0 social=6.0 fundamentals=6.6 | price=$458.79
MU: composite=6.96 | momentum=10.0 volume=1.5 news=10.0 social=6.0 fundamentals=7.2 | price=$795.33
RKLB: composite=7.10 | momentum=10.0 volume=2.9 news=10.0 social=6.0 fundamentals=6.8 | price=$117.35
PANW: composite=6.61 | momentum=10.0 volume=1.0 news=10.0 social=3.6 fundamentals=5.8 | price=$213.66
NVDA: composite=7.50 | momentum=10.0 volume=5.0 news=10.0 social=8.0 fundamentals=8.5 | price=$135.00
AAPL: composite=6.20 | momentum=7.0 volume=1.0 news=9.0 social=5.0 fundamentals=6.0 | price=$210.00
MSFT: composite=6.80 | momentum=8.0 volume=1.5 news=9.5 social=5.5 fundamentals=7.8 | price=$415.00
"""


def main():
    print(f"Querying Ollama at {OLLAMA_URL} with model {MODEL}\n{'='*60}")

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": USER},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=120,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        return

    data = resp.json()
    raw_text = data.get("message", {}).get("content", "")

    print("=== RAW LLM RESPONSE ===\n")
    print(repr(raw_text))
    print("\n=== RENDERED ===\n")
    print(raw_text)

    print("\n=== PARSE ATTEMPT ===\n")
    # Step 1: strip think blocks
    step1 = re.sub(r"<\|?think\|?>.*?</?\|?think\|?>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
    print(f"After think-block strip:\n{repr(step1[:500])}\n")

    # Step 2: strip markdown fences
    step2 = re.sub(r"```[a-z]*\n?", "", step1).strip()
    print(f"After fence strip:\n{repr(step2[:500])}\n")

    # Step 3: extract JSON array
    start = step2.find("[")
    end = step2.rfind("]")
    print(f"Array brackets: start={start}, end={end}")
    if start != -1 and end != -1:
        candidate = step2[start:end + 1]
        print(f"Extracted array:\n{candidate}\n")
        try:
            parsed = json.loads(candidate)
            print(f"[OK] Parsed successfully: {len(parsed)} items")
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError as e:
            print(f"[FAIL] json.loads error: {e}")
    else:
        print("[FAIL] No JSON array found in response")


if __name__ == "__main__":
    main()
