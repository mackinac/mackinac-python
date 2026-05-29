# Changelog

## 0.1.1 — 2026-05-29

New venue, new auth helper, several robustness fixes shaken out by running
the live test suite and example smoke against production.

### Added
- **dYdX V4 perp** as a first-class venue.  Subscribe with `dydx:<BASE>-USD`
  (e.g. `dydx:ETH-USD`).  Emits `QuoteMessage`, `PrintMessage`, and
  `FundingMessage` like Hyperliquid.  New `mackinac.symbols.dydx_perp()`
  helper produces the canonical `BASE-USD` form (idempotent).
- `AsyncClient.from_token()` and `Mackinac.from_token()` — sniff the
  credential prefix (`mk_*` → API key, anything else → JWT) so scripts
  and CLIs can take a single `MACKINAC_TOKEN` without branching on its type.
- `SubscribedMessage` and `SnapshotMessage` model types, surfacing the
  server's split between subscribe acknowledgements and historical
  ring-buffer payloads.  Both are part of the `FeedMessage` discriminated
  union.
- `examples/funding_carry.py` — companion to the blog post comparing
  CME deterministic carry, HL variable perpetual funding, and Ostium's
  real-world commodity carry over a shared notional.

### Changed
- WS engine: `max_size` raised to 10 MB so the initial HL full-book
  snapshot doesn't trip the websockets-library default and cause a
  silent close-1009 reconnect loop.  Documented in the README for
  users wiring up raw `websockets.connect()`.
- WS engine: subscribe ack is now a tiny `SubscribedMessage`; the
  initial print ring-buffer is requested explicitly via
  `{"action": "history"}` after each subscribe.  Transparent to callers —
  the library issues the history request automatically.
- WS engine: rejected symbols (`symbol_limit_reached`, `invalid_symbol`,
  `unknown_symbol`) are dropped from the active-subscription set so
  reconnect no longer retries them in a tight loop.
- WS engine `_dedup_key` now handles dYdX's blockNumber-only prints
  with `(exchange, symbol, block, time, price, size, side)`.  AMM
  (`block, tx`) and HL (`time, price, size, side`) branches unchanged.
- REST history paths now URL-encode the symbol, so slash-containing
  symbols like `XAU/USD` no longer hit the SPA catch-all and return HTML.
- `examples/multi_venue_basis.py`: third venue swapped from `lighter:ETH`
  to `dydx:ETH-USD`; remains a 3-symbol anonymous-cap example or `MACKINAC_TOKEN`-keyed.
- `tests/test_live.py` learned `--server=prod` (defaults to dev) and
  honours `MACKINAC_TOKEN`.  Symbol-cap assertions accept either
  `symbol_limit_reached` (per-session) or `free_tier_cap_reached`
  (per-IP) — both are valid cap responses depending on environment.

### Removed
- `mackinac.symbols.lighter_perp`.  The Lighter feed is disabled
  upstream pending regulatory review; `dydx_perp` is its
  documented replacement.

### Verified
- `pytest -m live --server=prod` → 14/14 passing
- All 11 example scripts produce expected output against
  `api.mackinac.io`

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
