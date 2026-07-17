from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # Output
    n_results: int = 50
    output_dir: str = "outputs_TA"
    output_filename: str = ""  # auto-generated if empty

    # Category weights (must sum to 1.0), split evenly within each category.
    # Attention is DISCOVERY ONLY, weight 0.00: Yahoo movers / StockTwits / Reddit / Finviz
    # already define the pool, so weighting them again counts them twice. Everything they
    # produce (buzz, rel_volume, momentum) is emitted for display and ranks nothing.
    # These are an explicit guess until Phase 3.4 fits them from IC.
    weights: dict = field(default_factory=lambda: {
        "fundamentals": 0.45,   # value, quality, growth
        "price_risk":   0.35,   # gold_gpa 0.175, max_drawdown 0.0875, volatility 0.0875
        "direction":    0.10,   # news_sentiment, social_sentiment
        "insider":      0.10,   # capitol_hill
    })
    # Within-category split. gold_gpa carries half of price_risk because the ladder is the
    # signal; max_drawdown and volatility split the rest.
    # `gold_score` is the 0-10 ranking signal (gold_gpa / 4 * 10 — exact, no divisor to rot).
    # `gold_gpa` stays the 0-4 report card and is display-only. They are deliberately separate
    # names: sharing one would let the 0-4 value overwrite the 0-10 signal in the output row.
    signal_weights: dict = field(default_factory=lambda: {
        "value": 1/3, "quality": 1/3, "growth": 1/3,
        "gold_score": 0.5, "max_drawdown": 0.25, "volatility": 0.25,
        "news_sentiment": 0.5, "social_sentiment": 0.5,
        "capitol_hill": 1.0,
    })
    signal_categories: dict = field(default_factory=lambda: {
        "value": "fundamentals", "quality": "fundamentals", "growth": "fundamentals",
        "gold_score": "price_risk", "max_drawdown": "price_risk", "volatility": "price_risk",
        "news_sentiment": "direction", "social_sentiment": "direction",
        "capitol_hill": "insider",
    })

    # Scoring windows
    momentum_window: int = 5        # days for recent return
    momentum_baseline: int = 90     # days for rolling σ baseline
    volume_avg_window: int = 20     # days for avg volume baseline
    lookback_days: int = 7          # news + social lookback

    # Price history — "max", not "10y": "10y" returns ~2,513 bars and the 10y ladder window
    # needs 2,520, so it silently produced zero 10y grades. Measured, not assumed.
    price_history_period: str = "max"

    # Multi-window ladder — trading days. Purpose: separate long-term compounders from
    # high-attention pumps. 6mo was dropped (rho +0.86 with 3mo — no extra view).
    ladder_windows: dict = field(default_factory=lambda: {
        "3mo": 63,      # is it hot right now (pump detector)
        "1y": 252,      # medium trend
        "2.5y": 630,    # holding-period-matched
        "5y": 1260,     # real track record
        "10y": 2520,    # is it actually a compounder
    })
    benchmark: str = "SPY"          # price/risk is market-relative, not pool-relative
    trading_days_per_year: int = 252

    # Grade cuts: per-window quantiles of a reference universe, recalibrated every run and
    # written into the snapshot. Freezing them was tested and rejected — the 3mo "A" line
    # ranged -0.76 to +2.65 across 2019-2026, so a frozen table encodes one regime and rots.
    # Determinism survives because replay reads the cuts it was scored with.
    reference_universe_size: int = 150
    grade_points: dict = field(default_factory=lambda: {
        "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
        "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "F": 0.0,
    })
    # Lower bound quantile for each grade, best first. Anything below the last is an F.
    grade_quantiles: dict = field(default_factory=lambda: {
        "A": 0.90, "A-": 0.80, "B+": 0.70, "B": 0.60, "B-": 0.50,
        "C+": 0.40, "C": 0.30, "C-": 0.20, "D+": 0.10, "D": 0.05,
    })

    # Monte Carlo — display + filter only, never the composite (P(goal) is rho 0.98 with
    # sharpe). Fixed seed so a replay reproduces the same paths.
    mc_horizon_days: int = 504      # ~2 trading years, the holding period
    mc_sims: int = 5000             # ~1.3 min for 400 tickers
    mc_goal: float = 0.50           # +50% over the horizon
    mc_bust: float = -0.50          # terminal-based, not maxdd (maxdd -20% is saturated)
    mc_seed: int = 20260716
    mc_bust_filter: float = 0.40    # drop names with P(bust) above this

    # Snapshots — ingest writes one, scoring is a pure function of it (--replay)
    snapshot_dir: str = "data/raw"

    # Universe seeding
    seed_pool_size: int = 400
    min_pool_size: int = 50         # trigger Wikipedia fallback below this

    # Risk window — horizon-matched to the 2-year hold, not the old 6mo
    risk_window: str = "2.5y"
    fundamentals_min_peers: int = 5

    # Sentiment. Lexicon v1 is an explicit guess until it is validated against StockTwits'
    # own bullish/bearish labels; `shrinkage_k` is what stops one word from scoring a 10.
    sentiment_shrinkage_k: float = 5.0
    sentiment_lexicon_core: dict = field(default_factory=lambda: {
        "positive": [
            "beat", "beats", "surge", "surges", "surged", "soar", "soars", "soared", "jump",
            "jumps", "jumped", "rally", "rallies", "gain", "gains", "rise", "rises", "rose",
            "climb", "climbs", "upgrade", "upgraded", "outperform", "record", "strong",
            "growth", "profit", "wins", "win", "approval", "approved", "raises", "raised",
            "bullish", "buyback", "expands", "boost", "boosted", "top", "tops", "topped",
        ],
        "negative": [
            "miss", "misses", "missed", "plunge", "plunges", "plunged", "tumble", "tumbles",
            "tumbled", "slump", "slumps", "fall", "falls", "fell", "drop", "drops", "dropped",
            "sink", "sinks", "sank", "downgrade", "downgraded", "underperform", "weak",
            "loss", "losses", "lawsuit", "probe", "investigation", "recall", "bearish",
            "cuts", "cut", "warns", "warning", "halts", "halted", "bankruptcy", "fraud",
            "slashes", "slashed", "slides", "slid", "crash", "crashes", "layoffs",
        ],
    })
    sentiment_lexicon_news: dict = field(default_factory=lambda: {
        "positive": ["outperformed", "beat estimates", "raises guidance", "price target raised"],
        "negative": ["below estimates", "cuts guidance", "price target cut", "sec probe",
                     "profit warning", "shares tumble", "shares plunge"],
    })
    sentiment_lexicon_social: dict = field(default_factory=lambda: {
        "positive": ["moon", "mooning", "calls", "yolo", "tendies", "squeeze", "printing",
                     "diamond hands", "to the moon", "buy the dip", "lfg"],
        "negative": ["puts", "bagholder", "bagholding", "dump", "dumping", "rug", "rugged",
                     "drilling", "red", "bloodbath", "dead cat", "loss porn"],
    })

    # Filters — deterministic gates. The honest version of the noise removal the LLM prompt
    # used to claim it was doing on numbers it could not see.
    min_price: float = 1.0
    min_avg_volume: int = 100_000
    max_drawdown_floor: float = -0.90    # drop names that have already lost ~everything once
    volatility_ceiling: float = 2.50     # annualised
    min_coverage: float = 0.40           # fraction of ranking signals actually observed
    min_history_years: float = 1.0

    # Reddit
    reddit_subreddits: List[str] = field(default_factory=lambda: [
        "wallstreetbets", "stocks", "investing", "Stocks_Picks", "ValueInvesting", "StockPickNews", "stocktraders", "algotrading"
    ])
    reddit_sort_orders: List[str] = field(default_factory=lambda: ["hot", "new"])
    reddit_limit_per_sub: int = 50
    reddit_min_mentions: int = 1

    # Performance
    max_workers: int = 5
    request_timeout: int = 10

    # Capitol Trades
    capitol_trades_pages: int = 3   # pages of recent trades to scrape (~60 days coverage)

    # Retry
    yfinance_retries: int = 2
    yfinance_retry_wait: int = 5    # seconds between attempts
