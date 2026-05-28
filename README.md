# mackinac-client

Python client for the [Mackinac](https://mackinac.io) market-data API — live
quotes, trades, funding rates, and yield rates across 12 DeFi venues including
Hyperliquid, Uniswap V3/V4, Pendle, Spectra, GMX, Vertex, Ostium, and more.

```
pip install mackinac-client
```

---

## Quick start

### Synchronous (no asyncio required)

No credentials required for free-tier access (3 concurrent symbols):

```python
from mackinac import Mackinac, QuoteMessage, PrintMessage

with Mackinac() as m:
    # What symbols are on HL?
    print(m.live_symbols("hl"))

    # Stream only quotes — types= filters the feed, no isinstance needed
    with m.subscribe("hl:ETH", types=QuoteMessage) as feed:
        for quote in feed:
            bid = quote.bids[0].price if quote.bids else None
            ask = quote.asks[0].price if quote.asks else None
            print(f"ETH  bid {bid}  ask {ask}")
            break  # just the first one

    # Stream only trades
    with m.subscribe("hl:ETH", types=PrintMessage) as feed:
        for trade in feed:
            side = "buy" if trade.side == 1 else "sell"
            print(f"ETH  {side}  {trade.price}  ×  {trade.size}")
            break
```

### Async (for existing asyncio code)

```python
import asyncio
from mackinac import AsyncClient, QuoteMessage

async def main():
    async with AsyncClient() as client:
        print(await client.live_symbols("hl"))

        async with client.subscribe("hl:ETH", types=QuoteMessage) as feed:
            async for quote in feed:
                print(f"ETH  bid {quote.bids[0].price}  ask {quote.asks[0].price}")
                break

asyncio.run(main())
```

---

## Authentication

Both `Mackinac` (sync) and `AsyncClient` (async) share the same constructors:

### API key (recommended for servers)
```python
m      = Mackinac.from_api_key("mk_live_...")       # sync
client = AsyncClient.from_api_key("mk_live_...")    # async
```
API keys are long-lived and authenticate WebSocket connections only.
Obtain them from the dashboard (requires tier `api`).

### JWT (browser / short-lived sessions)
```python
m      = Mackinac.from_jwt("eyJhbGciOi...")
client = AsyncClient.from_jwt("eyJhbGciOi...")
```
JWTs expire after 7 days.  Refresh via `client.refresh_token()` / `await client.refresh_token()`.

### Wallet sign-in (EIP-191)
```python
pip install 'mackinac-client[wallet]'
```
```python
m      = Mackinac.from_wallet(private_key="0xdeadbeef...", address="0xYourWalletAddress")
client = await AsyncClient.from_wallet(
    private_key="0xdeadbeef...",
    address="0xYourWalletAddress",
)
```

---

## Subscribing to live data

```python
async with client.subscribe("hl:ETH", "uni:WETH/USDC", "rates:all") as feed:
    async for msg in feed:
        match msg.type:
            case "quote":
                print(msg.exchange, msg.symbol, msg.bids[0].price)
            case "print":
                print(msg.price, msg.size, msg.side)  # side: 0=sell 1=buy
            case "rate_market":
                print(msg.symbol, f"{msg.impliedApy * 100:.2f}% APY")
            case "funding":
                print(msg.symbol, f"{msg.ratePct:.4f}% ann.")
```

All messages are typed Pydantic v2 models.  Use `isinstance()` or `match`
on `msg.type` to branch per message type.

### Subscribe key format

| Venue | Key format | Example |
|-------|-----------|---------|
| Hyperliquid perp | `hl:<SYMBOL>` | `hl:ETH` |
| Uniswap V3 (Arbitrum) | `uni:<BASE>/<QUOTE>` | `uni:WETH/USDC` |
| Uniswap V4 (Arbitrum) | `univ4:<BASE>/<QUOTE>` | `univ4:WETH/USDC` |
| SushiSwap V3 | `sushi:<BASE>/<QUOTE>` | `sushi:WETH/USDC` |
| PancakeSwap V3 | `pancake:<BASE>/<QUOTE>` | `pancake:WBTC/WETH` |
| GMX perp | `gmx:<SYMBOL>` | `gmx:BTC` |
| Vertex perp | `vertex:<SYMBOL>` | `vertex:SOL` |
| Ostium (RWA) | `ostium:<BASE>/<QUOTE>` | `ostium:XAU/USD` |
| Pendle/Spectra (all) | `rates:all` | — |
| Pendle/Spectra (trades) | `rates:swaps` | — |
| Specific yield market | `rates:<symbol-or-address>` | `rates:PT-weETH-25JUN2026` |
| AMM consolidated NBBO | `ammbook:<BASE>/<QUOTE>` | `ammbook:WETH/USDC` (professional+) |

Use `mackinac.symbols` helpers to construct keys safely:
```python
from mackinac import symbols

symbols.amm_pair("WETH", "USDC")        # "WETH/USDC"
symbols.ostium_pair("XAU")              # "XAU/USD"
symbols.pendle_address("0xC62D...")     # "0xc62d..."  (lowercased)
symbols.rates_all()                     # "rates:all"
```

### Unsubscribing mid-session

```python
await feed.unsubscribe("hl:ETH")
```

### Auto-reconnect

The library reconnects automatically on drops (1s → 2s → 4s → … → 30s cap)
and re-subscribes all active symbols.  The `async for` loop continues
seamlessly — no user-side retry logic needed.

### Raw websockets note

If you connect with the `websockets` library directly (rather than via `AsyncClient`),
set `max_size` to at least 10 MB.  The initial trade snapshot sent on subscribe can
exceed the library's 1 MB default:

```python
async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
    ...
```

`AsyncClient` already sets this internally.

---

## REST methods

### Symbol discovery

```python
# Which exchanges are live?
await client.markets()                        # dict[exchange, MarketStatus]

# All subscribable symbols on one venue
await client.live_symbols("hl")              # list[str]
await client.live_symbols("pendle")          # list[str]

# All venues at once
await client.live_symbols()                  # dict[exchange, list[str]]

# Symbols with persisted history
await client.historical_symbols("hl")        # list[str]

# Which venues quote ETH?
await client.instrument("ETH")               # InstrumentVenues
```

### Historical data

History iterators paginate automatically — no cursor handling needed:

```python
# Trades
async for trade in client.history_trades("hl", "ETH",
                                          start="2026-04-01",
                                          end="2026-04-08"):
    print(trade.time, trade.price, trade.size, trade.side)

# 5-second quote snapshots
async for snap in client.history_quotes("uni", "WETH/USDC",
                                         start="2026-04-01"):
    print(snap.time, snap.bids[0].price if snap.bids else None)

# Funding rates
async for fr in client.history_funding("hl", "ETH"):
    print(fr.ratePct, fr.intervalHrs)

# Yield-market snapshots
async for rate in client.history_rates("0xc62d...", start="2026-03-01"):
    print(rate.impliedApy, rate.tvl)
```

All methods accept `start`/`end` as ISO 8601 strings or epoch milliseconds.
Default range: last 24 hours.  Maximum lookback: 1 day (free tier) or 90 days (professional/api).

### Account

```python
await client.me()                  # JWT claims
await client.subscription_status() # current tier + expiry (re-reads on-chain)
await client.refresh_token()       # new 7-day JWT with updated tier claims
```

---

## Message types

| Type | Description | Venues |
|------|-------------|--------|
| `QuoteMessage` | Top-of-book snapshot | All |
| `PrintMessage` | Trade execution | CLOB, AMM, Oracle*, Yield |
| `FundingMessage` | Perpetual funding rate | HL, GMX, Vertex, Ostium |
| `DepthMessage` | Concentrated-liquidity tick snapshot + market impact | AMM |
| `LiquidityMessage` | LP Mint/Burn event | AMM |
| `RateMarketMessage` | Yield-market snapshot | Pendle, Spectra |
| `RateDepthMessage` | Depth-at-size APY quote | Pendle only |
| `AmmBookMessage` | Consolidated AMM NBBO (professional+) | Virtual |
| `AmmLiquiditySnapshotMessage` | LP event backfill on subscribe (professional+) | Virtual |
| `ArbFlagMessage` | Cross-venue arb gap signal (super_admin) | Virtual |
| `SpreadMessage` | Same-venue cross-tier spread (professional+) | Uni, Univ4 |
| `FeedStaleMessage` | Feed health: stale | Broadcast |
| `FeedLiveMessage` | Feed health: recovered | Broadcast |
| `ServerClosingMessage` | Graceful shutdown notice | Broadcast |
| `ErrorMessage` | Error frame | Server response |

*GMX and Vertex do not emit `PrintMessage` (oracle settle on net positions).

### Key field conventions

- **`time`** — always epoch milliseconds (`int`)
- **`side`** — `0` = aggressive sell (bid hit), `1` = aggressive buy (ask lift), `2` = unknown
- **`ratePct`** (FundingMessage) — annualized percentage, e.g. `10.95` = 10.95%/yr
- **`impliedApy`** (RateMarketMessage) — decimal fraction, e.g. `0.058` = 5.8%
- **`ptPrice`** — Pendle: USD price; Spectra: fraction of IBT
- **`tvl`** — Pendle: USD; Spectra v1: underlying-asset units (no USD oracle)
- **`amount0`/`amount1`/`amount`** (LiquidityMessage) — decimal strings in raw ERC-20 units

---

## Tiers & limits

| Tier | WS symbol cap | `ammbook` / `spread` | Historical data |
|------|:---:|:---:|:---:|
| Free (anonymous) | 3 | — | 1 day |
| Professional | 50 | ✓ | 90 days |
| API | 100 | ✓ | 90 days |

---

## Error handling

```python
from mackinac.exceptions import (
    AuthError,      # 401 / WS auth_error
    TierError,      # 403 / WS subscription_required
    RateLimitError, # 429 / WS rate_limited — has .retry_after
    SymbolLimitError,
    InvalidSymbolError,
    ServerError,    # 5xx / WS internal_error
)

try:
    async with client.subscribe("ammbook:WETH/USDC") as feed:
        ...
except TierError:
    print("Upgrade to professional tier for ammbook access")
```

- REST 4xx → typed exception immediately (no retry)
- REST 5xx → retried 3× with exponential backoff, then `ServerError`
- WS `auth_error` / `subscription_required` → raised, reconnect stops
- Other WS errors → delivered as `ErrorMessage` to the iterator

---

## Installing extras

```bash
pip install 'mackinac-client[wallet]'   # EIP-191 wallet sign-in
pip install 'mackinac-client[tables]'   # pandas, for amm_fee_table + rate_table examples
pip install 'mackinac-client[dev]'      # testing + model codegen
```

---

## Examples

| File | What it shows |
|------|---------------|
| `examples/subscribe_quotes.py` | HL ETH live top-of-book |
| `examples/historical_trades.py` | 7-day Ostium XAU/USD → CSV |
| `examples/yield_rates.py` | Pendle + Spectra live APY table |
| `examples/reconnect_pattern.py` | Iterator survives forced disconnect |
| `examples/multi_venue_basis.py` | Cross-venue ETH basis across CLOB, AMM, and oracle venues |
| `examples/amm_fee_table.py` | AMM depth → pandas fee-tier impact table |
| `examples/rate_table.py` | rate_market stream → pandas DataFrame |
| `examples/funding_carry.py` | CME vs HL vs Ostium carry cost comparison |

---

## Versioning

`mackinac.__version__` follows the library release.
`mackinac.__protocol_version__` matches the API schema version; a major bump
means a breaking wire-format change.

---

## License

MIT
