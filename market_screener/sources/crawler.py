"""
Shared crawl4ai driver.

Two sources need a real browser: Capitol Trades (JS-rendered tables) and Reddit (whose free
`.json` API now 403s for every HTTP client — including cloudscraper — while the plain HTML
page still serves 200). Rather than let each grow its own copy of the browser + event-loop
handling, they share this one. Duplicated fetchers drift apart: the same class of bug left one
Wikipedia fetcher with a User-Agent and its twin returning 403 (tasks/lessons.md).
"""
import asyncio
from typing import List


async def _scrape_async(urls: List[str], timeout_ms: int, wait_until: str, delay: float) -> List[dict]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    run_cfg = CrawlerRunConfig(
        wait_until=wait_until,
        page_timeout=timeout_ms,
        delay_before_return_html=delay,
    )
    pages: List[dict] = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        for url in urls:
            try:
                r = await crawler.arun(url=url, config=run_cfg)
                if r.success:
                    pages.append({
                        "url": url,
                        "status": getattr(r, "status_code", None),
                        "html": r.html or "",
                        "markdown": str(r.markdown or ""),
                    })
                else:
                    print(f"[WARN] crawl failed: {url}")
            except Exception as e:
                print(f"[WARN] crawl error ({url}): {e}")
    return pages


def scrape_urls(
    urls: List[str],
    timeout_ms: int,
    wait_until: str = "networkidle",
    delay: float = 2.0,
) -> List[dict]:
    """Fetch each URL in one headless browser session. Returns [{url, status, html, markdown}].

    Never raises — a dead source degrades the pool, it never crashes the run.
    """
    try:
        return asyncio.run(_scrape_async(urls, timeout_ms, wait_until, delay))
    except RuntimeError:
        # Already inside a running event loop (e.g. Jupyter)
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.get_event_loop().run_until_complete(
                _scrape_async(urls, timeout_ms, wait_until, delay)
            )
        except Exception as e:
            print(f"[WARN] crawl event loop error: {e}")
            return []
    except Exception as e:
        print(f"[WARN] crawl unavailable: {e}")
        return []
