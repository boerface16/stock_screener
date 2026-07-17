from datetime import datetime, time
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def is_market_open() -> bool:
    """Return True if the US equity market is currently in regular session (9:30–16:00 ET, Mon–Fri)."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:
        return False
    return _OPEN <= now.time() < _CLOSE
