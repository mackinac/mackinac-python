"""Tests for WS message model parsing.

Each test exercises a representative JSON fixture from the API schema examples
and verifies the discriminated union routes to the correct Pydantic model.
"""
import pytest
from pydantic import TypeAdapter

from mackinac.models import FeedMessage, _feed_adapter
from mackinac.models.messages import (
    AmmBookMessage,
    AmmLiquiditySnapshotMessage,
    ArbFlagMessage,
    AuthedMessage,
    DepthMessage,
    ErrorMessage,
    FeedLiveMessage,
    FeedStaleMessage,
    FundingMessage,
    LendingActionMessage,
    LiquidityMessage,
    PrintMessage,
    QuoteMessage,
    RateDepthMessage,
    RateMarketMessage,
    RateModelParamsMessage,
    ServerClosingMessage,
    SpreadMessage,
)

# ── Fixtures (minimal valid examples from the JSON schemas) ───────────────────

QUOTE = {
    "type": "quote", "exchange": "hl", "symbol": "ETH",
    "bids": [{"price": 3499.5, "size": 12.4}],
    "asks": [{"price": 3500.5, "size": 8.7}],
    "time": 1748275200000,
}

PRINT_HL = {
    "type": "print", "exchange": "hl", "symbol": "ETH",
    "price": 3500.25, "size": 1.4, "side": 1, "time": 1748275200500,
    "d_tickrate": 4.2, "d_volumerate": 12.7, "d_lobimb": -0.12,
    "d_hawkes": 6.1, "d_hawkesB": 2.4, "d_hawkesA": 3.7,
    "d_volumeimb": -3.4, "d_quoterate": 18.0,
}

PRINT_AMM = {
    "type": "print", "exchange": "uni", "symbol": "WETH/USDC",
    "price": 3500.12, "size": 2.7, "side": 0, "time": 1748275201200,
    "tick": 196234, "blockNumber": 290845001, "txIndex": 12,
    "logSender": "0x1111111254eeb25477b68fb85ed929f73a960582",
}

FUNDING = {
    "type": "funding", "exchange": "hl", "symbol": "ETH",
    "ratePct": 10.95, "intervalHrs": 8, "time": 1748275200000,
}

DEPTH = {
    "type": "depth", "exchange": "uni", "symbol": "WETH/USDC",
    "currentTick": 196234, "time": 1748275200000,
    "ticks": [{"tick": 195000, "price": 3499.5, "liquidityDelta": 1000.5, "cumLiquidity": 50000}],
    "impacts": [{"usd": 1000, "buyPrice": 3500.35, "sellPrice": 3499.65, "buyPct": 0.02, "sellPct": 0.02}],
}

LIQUIDITY = {
    "type": "liquidity", "exchange": "uni", "symbol": "WETH/USDC",
    "feeTier": 500, "action": "mint",
    "tickLower": 195000, "tickUpper": 197000,
    "amountUsd": 25000, "time": 1748275200000,
    "amount": "12500000000000000000",
    "amount0": "3570000000000000000",
    "amount1": "12500000000",
    "owner": "0xabc0000000000000000000000000000000000000",
    "blockNumber": 290845001, "txIndex": 17,
}

RATE_MARKET = {
    "type": "rate_market", "exchange": "pendle", "chain": "ethereum",
    "address": "0x0000000000000000000000000000000000000001",
    "symbol": "PT-weETH-25JUN2026",
    "underlyingApy": 0.031, "impliedApy": 0.058, "lpApy": 0.012,
    "ptPrice": 0.985, "ytPrice": 0.015,
    "expiry": 1751155200000, "daysToExpiry": 28.5,
    "tvl": 12500000, "volume24h": 450000, "tradingFeeRate": 0.001,
    "time": 1748275200000,
}

RATE_DEPTH = {
    "type": "rate_depth", "exchange": "pendle", "symbol": "PT-weETH-25JUN2026",
    "midRate": 0.058, "underlyingRate": 0.031, "ptPrice": 0.985,
    "poolFeeBps": 1.0, "tvl": 12500000, "daysToExpiry": 28.5,
    "levels": [{"sizeUsd": 10000, "buyRate": 0.056, "sellRate": 0.060, "spreadBps": 40}],
    "time": 1748275200000,
}

RATE_MARKET_LENDING = {
    "type": "rate_market", "exchange": "aave", "chain": "arbitrum",
    "address": "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
    "symbol": "USDC", "asset": "USDC",
    "underlyingApy": 0.0274, "borrowApy": 0.0372,
    "utilization": 0.822, "available": 9500000, "tvl": 53400000,
    "impliedApy": 0.0274, "lpApy": 0, "ptPrice": 1, "ytPrice": 0,
    "expiry": 0, "daysToExpiry": 0, "volume24h": 0,
    "time": 1748275200000,
}

LENDING_ACTION = {
    "type": "lending_action", "exchange": "aave", "chain": "arbitrum",
    "asset": "USDC", "market": "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
    "action": "borrow",
    "user": "0xabcdef0000000000000000000000000000000000",
    "onBehalfOf": "0xabcdef0000000000000000000000000000000000",
    "amount": "1500000000", "amountUsd": 1500.0, "rateAtTime": 0.0372,
    "blockNumber": 290845001, "txIndex": 17,
    "logSender": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "time": 1748275200000,
}

LENDING_LIQUIDATE = {
    "type": "lending_action", "exchange": "morpho", "chain": "arbitrum",
    "asset": "USDC", "market": "0x" + "a" * 64,
    "action": "liquidate",
    "user": "0xborrower000000000000000000000000000000aa",
    "liquidator": "0xliquidator00000000000000000000000000a000",
    "amount": "5000000000", "amountUsd": 5000.0,
    "collateralAsset": "wstETH",
    "collateralAmount": "1500000000000000000",
    "blockNumber": 290845200, "txIndex": 4,
    "logSender": "0x6c247b1f6182318877311737bac0844baa518f5e",
    "time": 1748275201500,
}

RATE_MODEL_PARAMS_AAVE = {
    "type": "rate_model_params", "exchange": "aave", "chain": "arbitrum",
    "market": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
    "asset": "WETH",
    "irmAddress": "0x429f16dba3b9e1900087cbaa7b50d38bc60fb73f",
    "baseRate": 0, "slope1": 0.025, "slope2": 0.08,
    "kink": 0.92, "reserveFactor": 0.15, "maxRate": 1.0,
    "time": 1748275200000,
}

RATE_MODEL_PARAMS_MORPHO = {
    "type": "rate_model_params", "exchange": "morpho", "chain": "arbitrum",
    "market": "0x" + "b" * 64, "asset": "USDC",
    "irmAddress": "0x66f30587fb8d4206918deb78eca7d5ebbafd06da",
    "targetUtil": 0.9, "curveSteepness": 4, "adjSpeed": 50,
    "time": 1748275200000,
}

AMMBOOK = {
    "type": "ammbook", "symbol": "WETH/USDC",
    "bids": [{"exchange": "uni", "price": 3500.15, "size": 3.9, "feeBps": 5, "time": 1748275200001}],
    "asks": [{"exchange": "sushi", "price": 3500.22, "size": 3.5, "feeBps": 5, "time": 1748275200000}],
    "midPrice": 3500.185, "spreadBps": 0.2, "time": 1748275200001,
}

AMMLIQ_SNAPSHOT = {
    "type": "ammliquidity_snapshot", "symbol": "WETH/USDC",
    "events": [LIQUIDITY],
}

ARBFLAG = {
    "type": "arbflag", "symbol": "WETH/USDC",
    "status": "open",
    "arbGap": {"buyExchange": "uni", "sellExchange": "sushi", "gapBps": 2.5, "gapUsd": 125},
    "time": 1748275200000,
}

SPREAD = {
    "type": "spread", "exchange": "uni", "symbol": "WETH/USDC",
    "bidPool": {"fee": 500, "price": 3500.50, "lastSwapMs": 1748275199000},
    "askPool": {"fee": 3000, "price": 3500.20, "lastSwapMs": 1748275198000},
    "spread": 0.30, "spreadPct": 0.0086, "depthBetween": 5.2,
    "time": 1748275200000,
}

FEED_STALE = {"type": "feed_stale", "exchange": "hl", "staleSec": 67.4}
FEED_LIVE  = {"type": "feed_live",  "exchange": "hl"}

SERVER_CLOSING = {"type": "server_closing", "reconnectIn": 5000}

AUTHED = {"type": "authed", "tier": "api", "symbolLimit": 100}

ERROR = {"type": "error", "code": "symbol_limit_reached",
         "message": "Tier 'none' allows 2 symbols", "retryAfter": 7}

# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fixture,expected_type", [
    (QUOTE,            QuoteMessage),
    (PRINT_HL,         PrintMessage),
    (PRINT_AMM,        PrintMessage),
    (FUNDING,          FundingMessage),
    (DEPTH,            DepthMessage),
    (LIQUIDITY,        LiquidityMessage),
    (RATE_MARKET,      RateMarketMessage),
    (RATE_MARKET_LENDING, RateMarketMessage),
    (RATE_DEPTH,       RateDepthMessage),
    (LENDING_ACTION,   LendingActionMessage),
    (LENDING_LIQUIDATE, LendingActionMessage),
    (RATE_MODEL_PARAMS_AAVE,   RateModelParamsMessage),
    (RATE_MODEL_PARAMS_MORPHO, RateModelParamsMessage),
    (AMMBOOK,          AmmBookMessage),
    (AMMLIQ_SNAPSHOT,  AmmLiquiditySnapshotMessage),
    (ARBFLAG,          ArbFlagMessage),
    (SPREAD,           SpreadMessage),
    (FEED_STALE,       FeedStaleMessage),
    (FEED_LIVE,        FeedLiveMessage),
    (SERVER_CLOSING,   ServerClosingMessage),
    (AUTHED,           AuthedMessage),
    (ERROR,            ErrorMessage),
])
def test_discriminated_union_routes_correctly(fixture, expected_type):
    msg = _feed_adapter.validate_python(fixture)
    assert isinstance(msg, expected_type), (
        f"Expected {expected_type.__name__}, got {type(msg).__name__}"
    )


def test_print_hl_has_stat_fields():
    msg = _feed_adapter.validate_python(PRINT_HL)
    assert isinstance(msg, PrintMessage)
    assert msg.d_hawkes == pytest.approx(6.1)
    assert msg.d_lobimb == pytest.approx(-0.12)
    assert msg.blockNumber is None


def test_print_amm_has_block_fields():
    msg = _feed_adapter.validate_python(PRINT_AMM)
    assert isinstance(msg, PrintMessage)
    assert msg.blockNumber == 290845001
    assert msg.txIndex == 12
    assert msg.d_hawkes is None


def test_rate_market_decimal_apys():
    msg = _feed_adapter.validate_python(RATE_MARKET)
    assert isinstance(msg, RateMarketMessage)
    assert msg.impliedApy == pytest.approx(0.058)
    assert msg.underlyingApy == pytest.approx(0.031)
    # PT-yield rows have no lending fields populated
    assert msg.borrowApy is None
    assert msg.utilization is None


def test_rate_market_lending_fields_populated():
    msg = _feed_adapter.validate_python(RATE_MARKET_LENDING)
    assert isinstance(msg, RateMarketMessage)
    assert msg.exchange == "aave"
    assert msg.asset == "USDC"
    assert msg.underlyingApy == pytest.approx(0.0274)  # supply APY
    assert msg.borrowApy == pytest.approx(0.0372)
    assert msg.utilization == pytest.approx(0.822)
    assert msg.available == pytest.approx(9_500_000)


def test_lending_action_borrow_carries_rate_at_time():
    msg = _feed_adapter.validate_python(LENDING_ACTION)
    assert isinstance(msg, LendingActionMessage)
    assert msg.action == "borrow"
    assert msg.rateAtTime == pytest.approx(0.0372)
    assert msg.amount == "1500000000"
    assert msg.collateralAsset is None  # not a liquidate event


def test_lending_action_liquidate_carries_collateral():
    msg = _feed_adapter.validate_python(LENDING_LIQUIDATE)
    assert isinstance(msg, LendingActionMessage)
    assert msg.action == "liquidate"
    assert msg.collateralAsset == "wstETH"
    assert msg.collateralAmount == "1500000000000000000"
    assert msg.liquidator is not None
    assert msg.rateAtTime is None  # not a borrow event


def test_rate_model_params_aave_branch():
    msg = _feed_adapter.validate_python(RATE_MODEL_PARAMS_AAVE)
    assert isinstance(msg, RateModelParamsMessage)
    assert msg.kink == pytest.approx(0.92)
    assert msg.slope1 == pytest.approx(0.025)
    assert msg.reserveFactor == pytest.approx(0.15)
    # Morpho-family fields stay None
    assert msg.targetUtil is None


def test_rate_model_params_morpho_branch():
    msg = _feed_adapter.validate_python(RATE_MODEL_PARAMS_MORPHO)
    assert isinstance(msg, RateModelParamsMessage)
    assert msg.targetUtil == pytest.approx(0.9)
    assert msg.curveSteepness == pytest.approx(4)
    # Aave/Compound-family fields stay None
    assert msg.kink is None
    assert msg.slope1 is None


def test_ammbook_optional_arbgap():
    # arbGap absent
    no_gap = dict(AMMBOOK)
    del no_gap  # suppress unused warning — we use AMMBOOK directly
    msg = _feed_adapter.validate_python(AMMBOOK)
    assert isinstance(msg, AmmBookMessage)
    assert msg.arbGap is None


def test_ammbook_with_arbgap():
    with_gap = dict(AMMBOOK)
    with_gap["arbGap"] = {"buyExchange": "uni", "sellExchange": "sushi", "gapBps": 1.5, "gapUsd": 75}
    msg = _feed_adapter.validate_python(with_gap)
    assert isinstance(msg, AmmBookMessage)
    assert msg.arbGap is not None
    assert msg.arbGap.gapBps == pytest.approx(1.5)


def test_error_retry_after():
    msg = _feed_adapter.validate_python(ERROR)
    assert isinstance(msg, ErrorMessage)
    assert msg.retryAfter == 7


def test_unknown_extra_fields_ignored():
    extended = dict(QUOTE)
    extended["future_field"] = "some_value"
    msg = _feed_adapter.validate_python(extended)
    assert isinstance(msg, QuoteMessage)
