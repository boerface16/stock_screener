from typing import Set
from config import Config


def fetch_finviz_tickers(cfg: Config) -> Set[str]:
    tickers: Set[str] = set()
    try:
        from finviz.screener import Screener

        filters_list = [
            [],                              # most active (no extra filter)
            ["ta_highlow52w_a50h"],          # near 52-week highs
            ["sh_avgvol_o500"],              # unusual volume (above 500k avg)
        ]
        for filters in filters_list:
            try:
                screen = Screener(filters=filters, order="volume", rows=100)
                for stock in screen:
                    sym = stock.get("Ticker", "").upper()
                    if sym and sym.isalpha() and 1 <= len(sym) <= 5:
                        tickers.add(sym)
            except Exception as e:
                print(f"[WARN] Finviz screener filter {filters} failed: {e}")

    except ImportError:
        print("[WARN] finviz package not installed, skipping Finviz source")
    except Exception as e:
        print(f"[WARN] Finviz unavailable (possibly blocked): {e}")

    return tickers
