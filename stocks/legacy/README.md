# Legacy data-collection scripts (superseded 2026-08-22)

These are the pre-marketdb scripts: one screener / benchmark / breadth script per universe,
the `data_fetch/` wrappers, the `config/study_*.py` dicts, the RRG / DeMark / drawdown scripts
and the six market-cap fetchers. Everything they did is now in `marketdb/` (see
`docs/marketdb_design.md`) — one price fetch, one metrics implementation, SQLite results.

They are kept for reference and for `tests/test_metrics_parity.py`, which imports them to prove
the new implementation reproduces their numbers. They still run against the old CSV watchlists
and write to `stocks/results/`, but nothing reads those files any more.
