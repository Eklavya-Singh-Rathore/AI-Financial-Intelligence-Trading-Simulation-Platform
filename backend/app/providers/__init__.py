"""Market-data provider abstraction (Phase 6).

A thin capability-keyed layer over external data sources. Every provider
degrades gracefully (returns []/None, never raises) - the news.py philosophy -
so a missing key or a flaky upstream can never break a request. The registry
picks the first *available* provider per capability by a configured priority.
"""
