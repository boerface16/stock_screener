from typing import Dict


def score_capitol_hill(ticker: str, trades: Dict[str, Dict]) -> float:
    """Net congressional buy activity scored 0–10. No data → 5 (neutral).

    Each weighted buy = +2 pts above neutral (5), each weighted sell = -1 pt.
    Recency weighting (last 14 days = 1.5×) is applied upstream in the trade dict.
    """
    if ticker not in trades:
        return 5.0

    data = trades[ticker]
    buy_w = data.get("buy_weight", 0.0)
    sell_w = data.get("sell_weight", 0.0)

    raw = (buy_w * 2.0) - (sell_w * 1.0)
    return round(max(0.0, min(10.0, 5.0 + raw)), 4)
