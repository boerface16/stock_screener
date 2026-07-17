import numpy as np
import pandas as pd


def score_momentum(hist: pd.DataFrame, momentum_window: int = 5, baseline: int = 90) -> float:
    """Z-score of recent return vs rolling σ, mapped 0–10."""
    if hist is None or len(hist) < baseline:
        return 5.0  # insufficient history → neutral

    try:
        closes = hist["Close"].dropna()
        if len(closes) < momentum_window + 2:
            return 5.0

        daily_returns = closes.pct_change().dropna()
        recent_return = (closes.iloc[-1] / closes.iloc[-(momentum_window + 1)] - 1)
        rolling_std = daily_returns.iloc[-baseline:].std()

        if rolling_std == 0 or np.isnan(rolling_std):
            return 5.0

        z = recent_return / rolling_std
        # Map z-score: -4σ → 0, 0 → 5, +4σ → 10
        score = 5.0 + (z / 4.0) * 5.0
        return float(np.clip(score, 0.0, 10.0))
    except Exception:
        return 5.0
