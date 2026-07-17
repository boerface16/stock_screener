from typing import Dict


def score_social(
    ticker: str,
    reddit_counts: Dict[str, int],
    st_ranks: Dict[str, int],
) -> float:
    """60% Reddit mention score + 40% StockTwits rank score."""
    # Reddit: saturates at 5 mentions → 10
    mention_count = reddit_counts.get(ticker, 0)
    reddit_score = min((mention_count / 5.0) * 10.0, 10.0)

    # StockTwits: best rank → 10, last place → 0, not trending → 0.
    # The list length is measured, not assumed: this was hardcoded to 50 while the endpoint
    # returns 30, so last place scored 4.08 instead of ~0 — a fossil constant of exactly the
    # kind tasks/lessons.md warns about. Derived from the data, it cannot go stale.
    st_rank = st_ranks.get(ticker)
    if st_rank is not None and len(st_ranks) > 1:
        last_rank = max(st_ranks.values())
        st_score = max(0.0, (last_rank - st_rank) / (last_rank - 1) * 10.0)
    elif st_rank is not None:
        st_score = 10.0  # only one trending symbol — it is, trivially, the top of the list
    else:
        st_score = 0.0

    return round(0.60 * reddit_score + 0.40 * st_score, 4)
