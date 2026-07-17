"""Tracking — paper-trade the screener's top picks per metric and follow forward returns.

Answers "which signal actually predicts gains?" Each dated CSV under `outputs_TA/` is a frozen
cohort: its top picks per metric are bought at that run's `price_usd`, ~$1000 each, and held
forever (cohort buy-and-hold, no selling). Nothing is persisted — cohorts are rebuilt from the
CSVs on disk and priced from a yfinance cache, so the whole tab is reproducible.
"""
