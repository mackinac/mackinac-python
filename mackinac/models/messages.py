"""Pydantic v2 models for every WebSocket feed message type.

Field names match the JSON wire format exactly (camelCase where the API uses
camelCase, snake_case where the API uses snake_case).  This preserves
one-to-one correspondence with the API documentation and JSON Schemas in
docs/api/schemas/.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

__all__ = [
    # Shared sub-objects
    "OrderLevel",
    "DepthImpact",
    "TickDepth",
    "AmmBookLevel",
    "AmmBookGap",
    "RateDepthLevel",
    "SpreadPool",
    # Feed messages
    "SubscribedMessage",
    "SnapshotMessage",
    "QuoteMessage",
    "PrintMessage",
    "FundingMessage",
    "DepthMessage",
    "LiquidityMessage",
    "RateMarketMessage",
    "RateDepthMessage",
    "LendingActionMessage",
    "RateModelParamsMessage",
    "AmmBookMessage",
    "AmmLiquiditySnapshotMessage",
    "ArbFlagMessage",
    "SpreadMessage",
    "FeedStaleMessage",
    "FeedLiveMessage",
    "ServerClosingMessage",
    "AuthedMessage",
    "ErrorMessage",
]

_cfg = ConfigDict(populate_by_name=True, extra="allow")


# ── Shared sub-objects ─────────────────────────────────────────────────────────

class OrderLevel(BaseModel):
    model_config = _cfg
    price: float
    size: float
    fee: Optional[int] = None          # AMM only — pool fee tier in ppm
    lastSwapMs: Optional[int] = None   # AMM only — epoch ms of last swap in pool


class DepthImpact(BaseModel):
    model_config = _cfg
    usd: float
    buyPrice: float
    sellPrice: float
    buyPct: float    # >= 0; cost to buy $usd of base vs mid
    sellPct: float   # >= 0; discount received selling $usd of base vs mid


class TickDepth(BaseModel):
    model_config = _cfg
    tick: int
    price: float
    liquidityDelta: float
    cumLiquidity: float


class AmmBookGap(BaseModel):
    """Cross-venue arb gap embedded in AmmBookMessage and ArbFlagMessage."""
    model_config = _cfg
    buyExchange: str   # venue with lowest ask — buy here
    sellExchange: str  # venue with highest bid — sell here
    gapBps: float
    gapUsd: float


class AmmBookLevel(BaseModel):
    model_config = _cfg
    exchange: str
    price: float
    size: float
    feeBps: Optional[float] = None
    time: Optional[int] = None
    impacts: Optional[list[DepthImpact]] = None


class RateDepthLevel(BaseModel):
    """One size tier in a Pendle depth-at-size APY quote."""
    model_config = _cfg
    sizeUsd: float
    buyRate: float    # APY locked in by buying PT (decimal fraction)
    sellRate: float   # APY implied by selling PT (decimal fraction)
    spreadBps: float


class SpreadPool(BaseModel):
    """One fee-tier pool in a SpreadMessage."""
    model_config = _cfg
    fee: int
    price: float
    lastSwapMs: int


# ── Feed messages ─────────────────────────────────────────────────────────────

class SubscribedMessage(BaseModel):
    """Acknowledgement sent immediately after a successful subscribe action.

    Confirms the server accepted the subscription and will begin streaming
    live messages for this (exchange, symbol) pair.  No historical data is
    attached — send a separate ``history`` action to receive the ring-buffer
    snapshot (the library does this automatically).
    """
    model_config = _cfg
    type: Literal["subscribed"]
    exchange: str
    symbol: str


class SnapshotMessage(BaseModel):
    """Historical print snapshot returned in response to a ``history`` action.

    Contains up to ``limit`` prints from the in-memory ring-buffer
    (default 500, server cap 1000), sorted oldest-first.  ``prints`` is
    empty if the feed has no buffered state for the symbol.

    ``reqId`` is echoed back verbatim if the request included one.
    """
    model_config = _cfg
    type: Literal["snapshot"]
    exchange: str
    symbol: str
    prints: list["PrintMessage"]
    reqId: Optional[str] = None


class QuoteMessage(BaseModel):
    """Top-of-book snapshot. Emitted on every L2 update for CLOB venues,
    on every on-chain Swap for AMM venues, and on every poll for oracle venues."""
    model_config = _cfg
    type: Literal["quote"]
    exchange: str
    symbol: str
    bids: list[OrderLevel]
    asks: list[OrderLevel]
    time: int  # epoch ms


class PrintMessage(BaseModel):
    """Single trade execution.

    The ``d_*`` stat-engine fields are present on Hyperliquid and dYdX prints.
    ``blockNumber`` is present on every on-chain venue (AMM, Ostium, dYdX,
    Pendle, Spectra).  ``txIndex``, ``logSender``, and ``tick`` are present
    only on EVM venues (AMM, Ostium, Pendle, Spectra) — dYdX prints carry
    ``blockNumber`` but not ``txIndex`` since the Cosmos chain orders many
    fills within a single block.
    """
    model_config = _cfg
    type: Literal["print"]
    exchange: Optional[str] = None  # absent on legacy HL messages — treat as "hl"
    symbol: str
    price: float
    size: float
    side: int   # 0=bid hit (sell), 1=ask lift (buy), 2=unknown
    time: int   # epoch ms

    # On-chain venues
    tick: Optional[int] = None
    blockNumber: Optional[int] = None
    txIndex: Optional[int] = None
    logSender: Optional[str] = None

    # HL stat-engine fields
    d_tickrate: Optional[float] = None
    d_volumerate: Optional[float] = None
    d_lobimb: Optional[float] = None    # LOB imbalance [-1, +1]
    d_bidqty: Optional[float] = None
    d_askqty: Optional[float] = None
    d_hawkes: Optional[float] = None    # Hawkes intensity, both sides
    d_hawkesB: Optional[float] = None   # Hawkes intensity, bid side
    d_hawkesA: Optional[float] = None   # Hawkes intensity, ask side
    d_volumeimb: Optional[float] = None # signed volume = bidVol - askVol (1s)
    d_quoterate: Optional[float] = None # L2 updates/sec (1s)


class FundingMessage(BaseModel):
    """Perpetual funding rate snapshot.

    ``ratePct`` is an ANNUALIZED percentage (not bps, not decimal fraction).
    Positive = longs pay shorts; negative = shorts pay longs.
    ``intervalHrs`` is the native venue payment cadence (HL=8, dYdX=8, GMX/Vertex=1, Ostium=24).
    """
    model_config = _cfg
    type: Literal["funding"]
    exchange: str
    symbol: str
    ratePct: float    # annualized %, e.g. 10.95 = 10.95% per year
    intervalHrs: int
    time: int


class DepthMessage(BaseModel):
    """Concentrated-liquidity tick snapshot + market-impact table.

    Emitted after each Mint/Burn event (throttled 200ms per symbol).
    AMM venues only (uni, univ4, univ4chain, sushi, pancake).
    """
    model_config = _cfg
    type: Literal["depth"]
    exchange: str
    symbol: str
    currentTick: int
    ticks: list[TickDepth]
    impacts: list[DepthImpact]  # at $1k/$10k/$100k/$1M; empty until tick data available
    time: int


class LiquidityMessage(BaseModel):
    """LP Mint or Burn event from an AMM pool.

    ``amount``, ``amount0``, ``amount1`` are decimal strings in raw token
    units (wei / raw ERC-20).  Divide by 10**decimals to get human units.
    """
    model_config = _cfg
    type: Literal["liquidity"]
    exchange: str
    symbol: str
    feeTier: int       # ppm: 100, 500, 2500, 3000, 10000
    action: str        # "mint" or "burn"
    tickLower: int
    tickUpper: int
    amountUsd: float
    time: int

    # Raw token amounts as decimal strings (18-decimal tokens)
    amount: str        # uint128 L delta
    amount0: str
    amount1: str

    owner: Optional[str] = None
    blockNumber: Optional[int] = None
    txIndex: Optional[int] = None


class RateMarketMessage(BaseModel):
    """Per-market snapshot.  Used by two venue families with overlapping fields:

    **Yield-rate venues** (Pendle, Spectra) — ``impliedApy``, ``ptPrice``,
    ``ytPrice``, ``expiry``, ``lpApy`` etc. carry the PT-fixed-rate story.
    Lending-specific fields (``borrowApy``, ``utilization``, ``available``)
    are absent.

    **Lending venues** (Aave V3, Compound V3, Morpho Blue) — ``underlyingApy``
    doubles as supply APY; ``borrowApy``, ``utilization``, ``available`` and
    (Morpho-only) ``rateAtTarget`` are populated.  PT-yield fields
    (``impliedApy``, ``ptPrice``, ``expiry``, ``daysToExpiry``, ``volume24h``)
    carry sentinel zeros on lending rows — branch on ``exchange`` ∈
    ``{"aave", "compound", "morpho"}`` when interpreting.

    All APY fields are DECIMAL FRACTIONS (0.131 = 13.1%/yr), not percentages.

    Venue-dependent ``ptPrice`` semantics (yield only):
    - Pendle = USD price
    - Spectra = fraction of IBT (1.0 = parity with underlying)

    Venue-dependent ``tvl`` semantics:
    - Pendle / lending venues = USD TVL
    - Spectra v1 = underlying-asset units (no USD oracle path yet)

    Use ``address`` as the unique market key with ``client.history_rates(addr)``.
    For Morpho specifically, ``address`` is the 32-byte ``id`` and ``symbol``
    is the ``LOAN/COLLATERAL`` pair string while ``asset`` holds just the loan
    asset (e.g. ``"USDC"``).
    """
    model_config = _cfg
    type: Literal["rate_market"]
    exchange: str          # "pendle", "spectra", "aave", "compound", or "morpho"
    chain: str
    address: str           # market contract address (or 32-byte id for Morpho)
    symbol: str            # PT symbol (yield) or asset/pair (lending)
    underlyingApy: float   # variable yield (yield) OR supply APY (lending)
    impliedApy: float      # fixed rate (yield); sentinel for lending
    lpApy: float           # LP reward APY; always 0 for Spectra v1 and lending
    ptPrice: float         # venue-dependent (yield); sentinel for lending
    ytPrice: float
    expiry: int            # epoch ms (yield); 0 for lending
    daysToExpiry: float    # 0 for lending
    tvl: float             # venue-dependent — see docstring
    volume24h: float       # 0 for Spectra v1 and lending
    tradingFeeRate: Optional[float] = None
    time: int

    # Lending-only fields (Aave / Compound / Morpho).  All Optional so the
    # model still validates against pure yield-rate rows.
    asset: Optional[str] = None          # loan asset symbol (e.g. "USDC")
    borrowApy: Optional[float] = None    # variable borrow APY (decimal)
    utilization: Optional[float] = None  # borrowed / supplied ratio in [0, 1]
    available: Optional[float] = None    # unborrowed USD currently in the pool
    rateAtTarget: Optional[float] = None # Morpho AdaptiveCurveIRM drift state


class RateDepthMessage(BaseModel):
    """Depth-at-size APY quote for a Pendle market (Pendle only, v1).

    All rates are DECIMAL FRACTIONS (0.058 = 5.8%).
    """
    model_config = _cfg
    type: Literal["rate_depth"]
    exchange: str
    symbol: str
    midRate: float
    underlyingRate: float
    ptPrice: float
    poolFeeBps: float
    tvl: float
    daysToExpiry: float
    levels: list[RateDepthLevel]
    time: int


class LendingActionMessage(BaseModel):
    """Discrete on-chain lending event (Aave V3, Compound V3, Morpho Blue).

    One frame per event — Supply / Withdraw / Borrow / Repay / Liquidate /
    FlashLoan — emitted in real time.

    ``amount`` is the raw uint256 token amount as a decimal STRING to preserve
    18-decimal-token precision; divide by ``10**decimals(asset)`` for human
    units (USDC=6, WBTC=8, most ERC-20s=18).  ``amountUsd`` is the
    platform-estimated USD notional when an oracle was wired at emit time —
    often absent on Morpho where many markets have no oracle.

    ``rateAtTime`` is populated only on Aave ``borrow`` events (the locked
    variable-borrow rate at borrow-time).  Compound recomputes per-block from
    utilisation so the field is omitted there.

    Liquidation events populate ``liquidator``, ``collateralAsset``, and
    ``collateralAmount``.

    ``(blockNumber, txIndex, logSender)`` uniquely identifies the on-chain
    event for dedup across resubscribes.
    """
    model_config = _cfg
    type: Literal["lending_action"]
    exchange: str          # "aave", "compound", or "morpho"
    chain: str             # "arbitrum" or "base"
    asset: str             # loan/base asset symbol (e.g. "USDC")
    market: str            # reserve / Comet / Morpho-id address
    action: Literal["supply", "withdraw", "borrow", "repay", "liquidate", "flashloan"]
    user: str              # raw lowercase EVM address
    amount: str            # raw uint256 as decimal string
    blockNumber: int
    txIndex: int
    logSender: str         # emitting contract address (lowercase)
    time: int              # epoch ms

    onBehalfOf: Optional[str] = None       # Aave: delegated supply/borrow target
    amountUsd: Optional[float] = None      # USD notional, oracle-dependent
    rateAtTime: Optional[float] = None     # locked variable borrow rate (Aave borrow only)
    collateralAsset: Optional[str] = None  # liquidate only
    collateralAmount: Optional[str] = None # liquidate only; raw uint256 decimal string
    liquidator: Optional[str] = None       # liquidate only; raw lowercase EVM address


class RateModelParamsMessage(BaseModel):
    """Interest Rate Model curve parameters for a lending market.

    Hourly per market with fingerprint-dedup on
    ``(exchange, chain, market)`` — unchanged params don't broadcast, so in
    steady state most markets emit once on first observation and go silent.

    Two IRM families share this message shape; branch on which fields are
    populated to pick the formula.

    **Aave V3 / Compound V3** (piecewise-linear kinked curve):
    populates ``baseRate``, ``slope1``, ``slope2``, ``kink``,
    ``reserveFactor`` (Aave), ``maxRate`` (Aave).  Reconstruct::

        if util <= kink:  apr = baseRate + slope1 * (util / kink)
        else:             apr = baseRate + slope1 + slope2 * ((util - kink) / (1 - kink))

    **Morpho Blue AdaptiveCurveIRM** (exponential drift):
    populates ``targetUtil``, ``curveSteepness``, ``adjSpeed``.  Combine with
    ``rateAtTarget(t)`` from the matching ``RateMarketMessage`` row::

        apr = rateAtTarget(t) * exp(curveSteepness * (util - targetUtil))

    All numeric fields are decimal APR (0.025 = 2.5%/yr), except utilisation
    fields (``kink``, ``targetUtil``) which are 0..1 ratios.
    """
    model_config = _cfg
    type: Literal["rate_model_params"]
    exchange: str          # "aave", "compound", or "morpho"
    chain: str             # "arbitrum" or "base"
    market: str            # reserve / Comet / Morpho-id address
    asset: str             # loan asset symbol
    irmAddress: str        # IRM strategy contract address
    time: int              # epoch ms

    # Aave / Compound (piecewise-linear)
    baseRate: Optional[float] = None
    slope1: Optional[float] = None
    slope2: Optional[float] = None
    kink: Optional[float] = None
    reserveFactor: Optional[float] = None  # Aave only
    maxRate: Optional[float] = None        # Aave only

    # Morpho AdaptiveCurveIRM (exponential)
    targetUtil: Optional[float] = None
    curveSteepness: Optional[float] = None
    adjSpeed: Optional[float] = None


class AmmBookMessage(BaseModel):
    """Consolidated AMM NBBO across all Arbitrum AMM venues.

    Gated: professional tier and above.
    ``arbGap`` is present only when the highest bid (across venues) exceeds
    the lowest ask (from a different venue).
    """
    model_config = _cfg
    type: Literal["ammbook"]
    symbol: str
    bids: list[AmmBookLevel]
    asks: list[AmmBookLevel]
    midPrice: float
    spreadBps: float
    arbGap: Optional[AmmBookGap] = None
    time: int


class AmmLiquiditySnapshotMessage(BaseModel):
    """Snapshot of up to 1000 recent LP events sent on ``ammliquidity`` subscribe.

    Sent ONCE per subscribe; subsequent events arrive as individual
    ``LiquidityMessage`` frames.  Gated: professional tier and above.
    """
    model_config = _cfg
    type: Literal["ammliquidity_snapshot"]
    symbol: str
    events: list[LiquidityMessage]


class ArbFlagMessage(BaseModel):
    """Edge-triggered cross-venue arb gap signal.

    ``status="open"`` fires when gap opens (includes ``arbGap`` detail).
    ``status="closed"`` fires when gap closes.
    Gated: super_admin role only.
    """
    model_config = _cfg
    type: Literal["arbflag"]
    symbol: str
    status: str   # "open" or "closed"
    arbGap: Optional[AmmBookGap] = None
    time: int


class SpreadMessage(BaseModel):
    """Same-venue cross-fee-tier spread signal (Uni V3/V4 only).

    Fires when bid-pool price > ask-pool price across different fee tiers.
    Gated: professional tier and above.
    """
    model_config = _cfg
    type: Literal["spread"]
    exchange: str   # "uni" or "univ4"
    symbol: str
    bidPool: SpreadPool
    askPool: SpreadPool
    spread: float       # $ spread (bidPool.price - askPool.price)
    spreadPct: float    # spread / askPool.price * 100
    depthBetween: Optional[float] = None
    time: int


class FeedStaleMessage(BaseModel):
    """Broadcast when a backend feed exceeds its staleness threshold."""
    model_config = _cfg
    type: Literal["feed_stale"]
    exchange: str
    staleSec: float   # seconds since last message from this feed


class FeedLiveMessage(BaseModel):
    """Broadcast when a stale feed recovers."""
    model_config = _cfg
    type: Literal["feed_live"]
    exchange: str


class ServerClosingMessage(BaseModel):
    """Graceful shutdown notice.  Reconnect after ``reconnectIn`` milliseconds."""
    model_config = _cfg
    type: Literal["server_closing"]
    reconnectIn: int   # ms


class AuthedMessage(BaseModel):
    """Confirmation frame sent after successful API-key authentication."""
    model_config = _cfg
    type: Literal["authed"]
    tier: str
    symbolLimit: Optional[int] = None   # None = unlimited (super_admin)


class ErrorMessage(BaseModel):
    """Error frame from the server.

    ``code`` identifies the error class; ``message`` is human-readable.
    ``retryAfter`` (seconds) is present on ``rate_limited`` errors.
    ``exchange`` / ``symbol`` identify which subscription triggered the error.
    ``limit`` is the cap that was exceeded (present on ``symbol_limit_reached``
    and ``free_tier_cap_reached``).
    """
    model_config = _cfg
    type: Literal["error"]
    code: Optional[str] = None
    message: Optional[str] = None
    retryAfter: Optional[int] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    limit: Optional[int] = None
