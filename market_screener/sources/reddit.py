import html as _html
import re
from typing import Dict, List, Set

from config import Config
from sources.crawler import scrape_urls

# Reddit's free .json API returns 403 for every HTTP client — plain requests, any User-Agent,
# and cloudscraper — and 403s even for a browser hitting the .json URL directly. The ordinary
# old.reddit HTML page still serves 200, so we render it and read the DOM instead. old.reddit
# is used over www because its markup is stable and carries data-timestamp per post.
_LISTING_URL = "https://old.reddit.com/r/{sub}/{sort}/"

# One <div class="thing" data-fullname="t3_..." data-timestamp="<ms>"> per post.
_POST_RE = re.compile(
    r'data-fullname="t3_[^"]+"(?P<attrs>[^>]*)>.*?'
    r'<a[^>]*class="[^"]*\btitle\b[^"]*"[^>]*>(?P<title>[^<]{1,300})</a>',
    re.DOTALL,
)
_TIMESTAMP_RE = re.compile(r'data-timestamp="(\d+)"')

_CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
_ALLCAPS_RE = re.compile(r"\b([A-Z]{2,5})\b")
# All-caps tokens that are also real tickers in the 7,070-name whitelist, so the whitelist
# cannot filter them. Each entry costs the genuine symbol (AI = C3.ai, EV, PT) but on these
# subreddits the acronym reading dominates by a wide margin — "AI" alone was 15 of 18 hits.
# Revisit if 2.9's buzz measurement says a name here is being unfairly starved.
_NOISE = {
    "CEO", "CFO", "COO", "CTO", "IPO", "FDA", "SEC", "ETF", "GDP", "CPI",
    "ATH", "ATL", "EPS", "PE", "DD", "IMO", "EOD", "EOW", "YTD", "YOY",
    "FOMO", "FUD", "YOLO", "TLDR", "WSB", "USA", "USD", "THE",
    "FOR", "AND", "NOT", "BUT", "ARE", "WAS", "HAS", "HAD", "ITS",
    # Modern subreddit vocabulary the original list predates
    "AI", "EV", "US", "UK", "EU", "OK", "PSA", "TA", "RIP", "LOL", "WTF",
    "ITM", "OTM", "DTE", "PT", "EOY", "NGL", "IIRC", "EDIT", "NEWS", "HODL",
    "BUY", "SELL", "HOLD", "CALL", "PUT", "GAIN", "LOSS", "RISK", "FED",
}


def _extract_tickers(text: str, valid_tickers: Set[str]) -> List[str]:
    found: List[str] = []

    # Cashtags first (high confidence) — case-insensitive, since "$nflx" is still a cashtag.
    for m in _CASHTAG_RE.finditer(text):
        t = m.group(1).upper()
        if t in valid_tickers:
            found.append(t)

    # All-caps fallback, matched against the ORIGINAL text. Upper-casing first turned every
    # 2-5 letter word in a title into a ticker candidate: ON, OR, YOU, IT, UP and NOW are all
    # real symbols in the 7,070-name whitelist, so "doubled down on ... now, it is up" scored
    # four mentions. Requiring genuine capitalisation is what makes this a signal at all.
    for m in _ALLCAPS_RE.finditer(text):
        t = m.group(1)
        if t not in _NOISE and t in valid_tickers and t not in found:
            found.append(t)

    return found


def _parse_listing(page_html: str, sub: str, limit: int) -> List[dict]:
    """Pull posts out of an old.reddit listing page.

    `selftext` is empty by design: a listing page carries titles only, and fetching each post's
    body would cost one browser page-load per post. Mentions therefore come from titles alone —
    a real reduction versus the old title+selftext scan, recorded rather than hidden.
    """
    posts: List[dict] = []
    for m in _POST_RE.finditer(page_html):
        ts_match = _TIMESTAMP_RE.search(m.group("attrs"))
        posts.append({
            "subreddit": sub,
            "title": _html.unescape(m.group("title")).strip(),
            "selftext": "",
            "created_utc": int(ts_match.group(1)) / 1000.0 if ts_match else 0,  # ms → s
        })
        if len(posts) >= limit:
            break
    return posts


def fetch_reddit_posts(cfg: Config) -> List[dict]:
    urls = [
        (sub, _LISTING_URL.format(sub=sub, sort=sort))
        for sub in cfg.reddit_subreddits
        for sort in cfg.reddit_sort_orders
    ]
    pages = scrape_urls(
        [u for _, u in urls],
        timeout_ms=cfg.request_timeout * 3 * 1000,
        wait_until="domcontentloaded",   # listing markup is server-rendered; no need to idle
        delay=0.0,
    )
    by_url = {p["url"]: p for p in pages}

    posts: List[dict] = []
    for sub, url in urls:
        page = by_url.get(url)
        if not page:
            continue
        if page["status"] and page["status"] != 200:
            print(f"[WARN] Reddit {url} returned HTTP {page['status']}")
            continue
        found = _parse_listing(page["html"], sub, cfg.reddit_limit_per_sub)
        if not found:
            print(f"[WARN] Reddit {url} parsed to 0 posts — markup may have changed")
        posts.extend(found)
    return posts


def extract_mentions(posts: List[dict], valid_tickers: Set[str], cfg: Config) -> Dict[str, int]:
    mention_counts: Dict[str, int] = {}
    for post in posts:
        text = f"{post['title']} {post['selftext']}"
        for ticker in _extract_tickers(text, valid_tickers):
            mention_counts[ticker] = mention_counts.get(ticker, 0) + 1

    return {
        t: count for t, count in mention_counts.items()
        if count >= cfg.reddit_min_mentions
    }
