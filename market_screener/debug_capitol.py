#!/usr/bin/env python3
"""
Run this to see exactly what crawl4ai scrapes from Capitol Trades.
Usage: python debug_capitol.py
"""
import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://www.capitoltrades.com/trades?pageSize=96&page=1"


async def main():
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(
        wait_until="networkidle",
        page_timeout=30000,
        delay_before_return_html=2.0,
    )

    print(f"Scraping: {URL}\n{'='*60}")
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=URL, config=run_cfg)

    if not result.success:
        print("Crawl failed.")
        return

    print("=== RAW MARKDOWN (first 3000 chars) ===\n")
    print(result.markdown[:3000])
    print("\n=== LINES CONTAINING '|' (table rows) ===\n")
    for line in result.markdown.splitlines():
        if '|' in line:
            print(repr(line))


asyncio.run(main())
