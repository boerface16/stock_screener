"""
Deterministic reason strings, built from the drivers that actually moved the rank.

The LLM used to write these. It saw six numbers per ticker — no headlines, no company name, no
market cap — yet its prompt asked it to strip "meme spikes with no news catalyst" and
"micro-caps". On 2026-05-15 it ranked DELL #4 with "high news coverage... indicating
institutional interest" on a day whose actual headlines were "shares tumble 14%".

A template cannot hallucinate, costs nothing, and cites the numbers the ranking actually used.
"""
from typing import Dict, List

_LABELS = {
    "value": "value", "quality": "quality", "growth": "growth",
    "gold_score": "vs-SPY record", "max_drawdown": "drawdown", "volatility": "volatility",
    "news_sentiment": "news tone", "social_sentiment": "social tone",
}


def build_reason(row: Dict[str, object], cfg) -> str:
    """Name the strongest and weakest contributors, plus the grade string and any caveats."""
    # capitol_hill is signed (-10..10, 0 neutral), so it can't share the 0-10 strong/weak
    # thresholds — a single congressional buy at +3.3 would read as "weak". It gets its own
    # sign-aware clause below and is excluded from the generic ranking here.
    scored = {
        name: float(row[name])
        for name in cfg.signal_weights
        if row.get(name) is not None and name != "capitol_hill"
    }
    if not scored:
        return "No ranking signals observed"

    ranked = sorted(scored.items(), key=lambda kv: -kv[1])
    strong: List[str] = [f"{_LABELS.get(n, n)} {v:.1f}" for n, v in ranked[:2] if v >= 6.0]
    weak: List[str] = [f"{_LABELS.get(n, n)} {v:.1f}" for n, v in ranked[-1:] if v <= 4.0]

    parts: List[str] = []
    if strong:
        parts.append("strong " + ", ".join(strong))
    if weak:
        parts.append("weak " + ", ".join(weak))
    if not parts:
        parts.append(f"balanced ({ranked[0][0]} {ranked[0][1]:.1f} highest)")

    cap = row.get("capitol_hill")
    if isinstance(cap, (int, float)):
        if cap >= 3.0:
            parts.append(f"congress buying {cap:+.1f}")
        elif cap <= -3.0:
            parts.append(f"congress selling {cap:+.1f}")

    grades = row.get("grades")
    if grades:
        parts.append(f"grades {grades}")

    caveats = _caveats(row, cfg)
    if caveats:
        parts.append("; ".join(caveats))
    return "; ".join(parts)


def _caveats(row: Dict[str, object], cfg) -> List[str]:
    out: List[str] = []
    cov = row.get("coverage")
    if isinstance(cov, (int, float)) and cov < 0.75:
        out.append(f"only {cov:.0%} of signals observed")
    wins = row.get("windows_available")
    if isinstance(wins, int) and wins < len(cfg.ladder_windows):
        out.append(f"{wins}/{len(cfg.ladder_windows)} windows")
    if row.get("meme_flag"):
        out.append("MEME FLAG")
    conf = row.get("mc_confidence")
    if isinstance(conf, (int, float)) and conf < 0.3:
        out.append("low MC confidence")
    return out
