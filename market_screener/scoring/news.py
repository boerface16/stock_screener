"""
News: fetch (ingest) + relevance filtering, buzz and sentiment (scoring).

The old query was `{ticker}+stock`, which is why AD returned Netflix ad-revenue pieces, LINK
returned a person named Link, and WRAP returned Bloomberg's "Markets Wrap". A bare ticker is a
common English word often enough that the feed was measuring the wrong company entirely.

The fix costs no extra request: ingest already has the `info` dict, so the company name is free.
Query on the quoted name, then keep only articles whose title actually refers to the company —
by cashtag, standalone (capitalised) ticker, or a distinctive company token.
"""
import re
import xml.etree.ElementTree as ET
from typing import List, Sequence
from urllib.parse import quote_plus

import requests

_GNEWS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Corporate suffixes carry no identifying information — "Inc" must not match every filing.
_SUFFIXES = {
    "inc", "inc.", "corp", "corp.", "corporation", "co", "co.", "company", "ltd", "ltd.",
    "limited", "plc", "llc", "lp", "holdings", "holding", "group", "the", "&", "sa", "nv",
    "ag", "se", "class", "common", "stock", "ordinary", "shares", "trust", "technologies",
    "technology", "international", "industries", "enterprises",
}


def company_tokens(name: str) -> List[str]:
    """Distinctive lowercase tokens from a company name, suffixes stripped."""
    if not name:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z0-9'&-]+", name)
    return [w.lower() for w in words if w.lower() not in _SUFFIXES and len(w) > 2]


def build_query(ticker: str, company_name: str, lookback_days: int) -> str:
    """Quoted company name + a hard recency bound. Falls back to the ticker when unnamed."""
    if company_name:
        base = f'"{company_name}" stock'
    else:
        base = f"{ticker} stock"
    return f"{base} when:{lookback_days}d"


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def is_relevant(title: str, ticker: str, tokens: Sequence[str]) -> bool:
    """Does this headline actually refer to this company?

    Three independent signals, any of which is sufficient:
      cashtag ($AD), standalone capitalised ticker (AD — case-sensitive, so "ad revenue"
      does not match), or a distinctive company token ("netflix").
    """
    if re.search(rf"\${re.escape(ticker)}\b", title, re.IGNORECASE):
        return True
    if re.search(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", title):
        return True   # case-sensitive on purpose
    low = title.lower()
    return any(tok in low for tok in tokens)


def fetch_news(ticker: str, company_name: str = "", lookback_days: int = 7,
               timeout: int = 10) -> List[dict]:
    """Network — ingest only. Returns relevant, deduped articles with titles and timestamps."""
    from email.utils import parsedate_to_datetime

    query = build_query(ticker, company_name, lookback_days)
    url = _GNEWS_URL.format(query=quote_plus(query))
    tokens = company_tokens(company_name)

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []

    items: List[dict] = []
    seen = set()
    for item in root.findall(".//item"):
        title = (item.findtext("title", "") or "").strip()
        if not title or not is_relevant(title, ticker, tokens):
            continue
        # Syndication: the same story reprinted by 12 outlets is one event, not twelve.
        key = _normalize_title(title)
        if key in seen:
            continue
        seen.add(key)
        try:
            ts = parsedate_to_datetime(item.findtext("pubDate", "")).timestamp()
        except Exception:
            ts = 0
        items.append({"title": title, "published": ts})
    return items


def recent_weighted_count(news_items: List[dict], now: float, lookback_days: int) -> float:
    """Articles inside the window, those under 2 days old counting 1.5x."""
    cutoff = now - (lookback_days * 86400)
    recent = now - (2 * 86400)
    total = 0.0
    for item in news_items:
        ts = item.get("published", 0)
        if ts >= cutoff:
            total += 1.5 if ts >= recent else 1.0
    return total
