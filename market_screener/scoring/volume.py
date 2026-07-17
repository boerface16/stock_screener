"""
Relative volume — display only.

This left the composite deliberately: "unusually active today" is attention, and attention
already defines the pool. Weighting it again double-counts it, and it says nothing about a
2-year hold.

It is also a cautionary tale about clipping. The old scorer mapped ratio<1 → 0.0, so every
stock merely trading below its 20-day average tied at the floor: 278 of 381 on a real pool.
The raw ratio is emitted instead, un-clipped, so nothing is destroyed by the mapping.
"""
from typing import Optional

import numpy as np
import pandas as pd


def volume_ratio(hist: Optional[pd.DataFrame], avg_window: int = 20) -> Optional[float]:
    """Most-recent volume ÷ trailing average. None when there is not enough history."""
    if hist is None or "Volume" not in hist or len(hist) < avg_window + 1:
        return None
    volumes = hist["Volume"].dropna()
    if len(volumes) < avg_window + 1:
        return None
    avg = volumes.iloc[-(avg_window + 1):-1].mean()
    if avg == 0 or not np.isfinite(avg):
        return None
    return round(float(volumes.iloc[-1] / avg), 4)
