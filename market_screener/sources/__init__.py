from dataclasses import dataclass, field
from typing import Dict, List, Set

from config import Config
from sources.yahoo import fetch_yahoo_movers, fetch_wikipedia_index
from sources.stocktwits import fetch_stocktwits_trending
from sources.reddit import fetch_reddit_posts, extract_mentions
from sources.finviz import fetch_finviz_tickers
from sources.ticker_universe import load_valid_tickers
from sources.capitol_trades import fetch_capitol_trades


@dataclass
class Seed:
    """Universe seeding output. `pool` is ordered, never a set — see rank_pool."""
    pool: List[str]
    confirmations: Dict[str, int]           # how many sources named each ticker
    st_ranks: Dict[str, int] = field(default_factory=dict)
    reddit_counts: Dict[str, int] = field(default_factory=dict)
    reddit_posts: List[dict] = field(default_factory=list)
    capitol_trades: Dict[str, Dict] = field(default_factory=dict)


def rank_pool(sources: Dict[str, Set[str]], cap: int) -> (List[str], Dict[str, int]):
    """
    Order the pool by source-confirmation count desc, then ticker asc, and cap it.

    The old code did `set(list(pool)[:400])`. Python randomizes string hash seeds per
    process, so that truncated an unordered collection: three runs produced three
    different universes from identical inputs. Ranking by confirmation count is both
    deterministic and a better cap — corroborated tickers survive, not arbitrary ones.
    """
    confirmations: Dict[str, int] = {}
    for names in sources.values():
        for t in names:
            confirmations[t] = confirmations.get(t, 0) + 1
    ranked = sorted(confirmations, key=lambda t: (-confirmations[t], t))
    return ranked[:cap], confirmations


def seed_universe(cfg: Config) -> Seed:
    print("[INFO] Loading ticker whitelist...")
    valid_tickers = load_valid_tickers(timeout=cfg.request_timeout)

    print("[INFO] Seeding universe from all sources...")

    yahoo_tickers = fetch_yahoo_movers(cfg)
    print(f"[INFO]   Yahoo movers: {len(yahoo_tickers)} tickers")

    st_tickers, st_ranks = fetch_stocktwits_trending(cfg)
    print(f"[INFO]   StockTwits trending: {len(st_tickers)} tickers")

    reddit_posts = fetch_reddit_posts(cfg)
    reddit_counts = extract_mentions(reddit_posts, valid_tickers, cfg)
    reddit_tickers = set(reddit_counts.keys())
    print(f"[INFO]   Reddit mentions: {len(reddit_tickers)} tickers")

    finviz_tickers = fetch_finviz_tickers(cfg)
    print(f"[INFO]   Finviz screeners: {len(finviz_tickers)} tickers")

    capitol_trades = fetch_capitol_trades(cfg, valid_tickers)

    sources: Dict[str, Set[str]] = {
        "yahoo": yahoo_tickers,
        "stocktwits": st_tickers,
        "reddit": reddit_tickers,
        "finviz": finviz_tickers,
        "capitol": set(capitol_trades.keys()),
    }

    total = len(set().union(*sources.values())) if sources else 0
    if total < cfg.min_pool_size:
        print(f"[WARN] Pool only {total} tickers — adding Wikipedia index fallback")
        sources["wikipedia"] = fetch_wikipedia_index()

    if valid_tickers:
        sources = {name: {t for t in s if t in valid_tickers} for name, s in sources.items()}
    else:
        print("[WARN] Ticker whitelist empty — skipping whitelist filter")

    pool, confirmations = rank_pool(sources, cfg.seed_pool_size)

    print(f"[INFO] Universe seeded: {len(pool)} tickers")
    return Seed(
        pool=pool,
        confirmations={t: confirmations[t] for t in pool},
        st_ranks=st_ranks,
        reddit_counts=reddit_counts,
        reddit_posts=reddit_posts,
        capitol_trades=capitol_trades,
    )
