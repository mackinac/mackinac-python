# Changelog

## 0.2.0 — 2026-05-29

Lending markets land as a first-class data type.  Aave V3, Compound V3, and
Morpho Blue join the SDK alongside Pendle / Spectra under the existing
`rate_market` family, plus two new message types for lending-specific data.

### Added
- **Aave V3 / Compound V3 / Morpho Blue** as lending venues on Arbitrum and Base.
- `LendingActionMessage` — discrete Supply / Withdraw / Borrow / Repay /
  Liquidate / FlashLoan events with on-chain attribution
  (`user`, `amount` as raw uint256 decimal string, `amountUsd`, `blockNumber`,
  `txIndex`, `logSender`).  Liquidation events also carry `liquidator`,
  `collateralAsset`, and `collateralAmount`.
- `RateModelParamsMessage` — Interest Rate Model curve parameters for
  backtest reconstruction.  Aave/Compound populate piecewise-linear fields
  (`baseRate`, `slope1`, `slope2`, `kink`, `reserveFactor`, `maxRate`);
  Morpho's AdaptiveCurveIRM populates `targetUtil`, `curveSteepness`, `adjSpeed`.
- `AsyncClient.history_lending_actions(exchange, asset, *, start, end, limit,
  chain=None, action=None)` and matching sync `Mackinac.history_lending_actions`.
  Paginates `/v1/history/lending/{exchange}/{asset}/actions`, yielding typed
  `HistoryLendingAction` rows.
- `AsyncClient.history_lending_model(exchange, asset, *, start, end, limit,
  chain=None)` and matching sync `Mackinac.history_lending_model`.  Yields
  typed `HistoryRateModelParams` rows.
- Eight new `mackinac.symbols` helpers: `aave_market`, `aave_all`,
  `compound_market`, `compound_all`, `morpho_market`, `morpho_all`,
  `morpho_market_id`, and `lending_actions` (consolidated topic).
- Four new example scripts demonstrating both topics in both API flavours:
  `lending_rates_{sync,async}.py` (supply/borrow APY table) and
  `liquidation_watch_{sync,async}.py` (live liquidation feed).  These are
  the first examples to ship in matched sync/async pairs so users can see
  the surface parity at a glance.

### Changed
- `RateMarketMessage` extended with five optional lending-only fields
  (`asset`, `borrowApy`, `utilization`, `available`, `rateAtTarget`).
  Existing Pendle/Spectra consumers are unaffected — all new fields are
  Optional and PT-yield rows omit them.  Branch on `msg.exchange` to
  interpret venue-dependent semantics.
- `HistoryRate` (REST) gains the same optional lending fields, so
  `history_rates(address)` returns rich rows for lending markets too.
- `_history_iter` now accepts an optional `extra_params` dict for endpoints
  with filter kwargs (used by `history_lending_actions` for `chain` / `action`).
- README intro tagline: `13 venues` → `16 venues`; adds Aave, Compound,
  Morpho to the named list.  New rows added to the symbol-prefix table
  and the message-types matrix.
- Examples table notes the new `_sync` / `_async` filename convention.

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
