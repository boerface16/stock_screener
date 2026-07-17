from typing import Dict, Optional


def score_capitol_hill(
    ticker: str,
    trades: Dict[str, Dict],
    buy_points: float = 3.3,
    sell_points: float = 3.3,
) -> Optional[float]:
    """Net congressional trading on a signed -10..10 scale. 0 is neutral; None means no data.

    Each weighted buy adds `buy_points`, each weighted sell subtracts `sell_points`, clamped to
    [-10, 10]. Recency weighting (last 14 days = 1.5x) is applied upstream in the trade dict.

    No trades -> None, so the signal renormalizes out of the composite rather than imputing a
    value: a stock Congress never touched is neutral, not penalized (unlike the old 5.0 default,
    which handed every untraded name a mediocre-but-positive score). Selling is treated as a real
    negative — members are poised to hold material non-public information, so a sell-off drags the
    composite down instead of merely failing to lift it.
    """
    data = trades.get(ticker)
    if not data:
        return None

    buy_w = data.get("buy_weight", 0.0)
    sell_w = data.get("sell_weight", 0.0)
    if buy_w == 0 and sell_w == 0:
        return None

    raw = buy_w * buy_points - sell_w * sell_points
    return round(max(-10.0, min(10.0, raw)), 4)
