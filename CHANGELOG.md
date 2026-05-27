# Changelog

## 0.1.0 — 2026-05-27

Initial release.

- `AsyncClient` and `Mackinac` (sync) clients
- Live WebSocket subscriptions with auto-reconnect and deduplication
- Type-filtered feeds via `types=` kwarg
- REST discovery: `markets()`, `live_symbols()`, `historical_symbols()`, `instruments()`
- Historical data iterators: `history_trades()`, `history_quotes()`, `history_funding()`, `history_rates()`
- Three authentication paths: API key, JWT, EIP-191 wallet sign-in
- Full Pydantic v2 models for all message and REST types
- Symbol helpers in `mackinac.symbols`
