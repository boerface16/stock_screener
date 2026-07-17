"""
Lexicon sentiment, absolute-scaled.

    score = 5 + 5 * rate * (n / (n + k))

`rate` = (pos - neg) / (pos + neg) has a real zero — genuinely balanced coverage *is* neutral —
so this is scaled absolutely rather than by percentile. A percentile would destroy that zero and
force half the pool to look bearish on a uniformly good news day.

The shrinkage term `n / (n + k)` is why one word does not make a verdict: a ticker with a single
positive headline lands near 5.0, and only sustained one-sided coverage reaches the extremes.
Without it, n=1 would score a perfect 10.0 — the same "1 article = maximum" failure that made
the old news scorer a constant.

Returns None when no lexicon word matched at all. That is "unmeasured", not "neutral", and it
must renormalize away rather than impute 5.0 (tasks/lessons.md).
"""
import re
from typing import Dict, List, Optional, Sequence

_WORD_RE = re.compile(r"[a-z']+")


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


def count_hits(texts: Sequence[str], positive: Sequence[str], negative: Sequence[str]) -> Dict[str, int]:
    """Count lexicon matches across texts. Multi-word entries are matched as substrings."""
    pos_single = {w for w in positive if " " not in w}
    neg_single = {w for w in negative if " " not in w}
    pos_multi = [w for w in positive if " " in w]
    neg_multi = [w for w in negative if " " in w]

    pos = neg = 0
    for text in texts:
        low = text.lower()
        toks = _tokens(low)
        pos += sum(1 for t in toks if t in pos_single)
        neg += sum(1 for t in toks if t in neg_single)
        pos += sum(low.count(p) for p in pos_multi)
        neg += sum(low.count(p) for p in neg_multi)
    return {"positive": pos, "negative": neg}


def score_from_counts(positive: int, negative: int, shrinkage_k: float = 5.0) -> Optional[float]:
    """Shrinkage-scaled sentiment from explicit pos/neg counts.

    The same map as the lexicon path, but the counts arrive pre-labeled rather than from a word
    match — this is how StockTwits Bull/Bear labels become social_sentiment. None when there are
    no labels: unmeasured, not neutral (must renormalize away, never impute 5.0).
    """
    n = positive + negative
    if n == 0:
        return None
    rate = (positive - negative) / n
    return round(5.0 + 5.0 * rate * (n / (n + shrinkage_k)), 4)


def sentiment_score(
    texts: Sequence[str],
    positive: Sequence[str],
    negative: Sequence[str],
    shrinkage_k: float = 5.0,
) -> Optional[float]:
    hits = count_hits(texts, positive, negative)
    return score_from_counts(hits["positive"], hits["negative"], shrinkage_k)


def merge_lexicon(core: Dict[str, List[str]], register: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Core terms plus a register-specific overlay (news prose vs social shorthand)."""
    return {
        "positive": list(core.get("positive", [])) + list(register.get("positive", [])),
        "negative": list(core.get("negative", [])) + list(register.get("negative", [])),
    }
