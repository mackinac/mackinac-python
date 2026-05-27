"""Pydantic v2 models for REST API responses.

Generated from docs/api/openapi.yaml — see codegen/generate.py to regenerate.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

__all__ = [
    # Discovery
    "Capabilities",
    "MarketStatus",
    "MarketsResponse",
    "ExchangeSummary",
    "SymbolsResponse",
    "ExchangeSymbolsDetail",
    "ExchangeSymbolsResponse",
    "InstrumentVenue",
    "InstrumentVenues",
    # History
    "HistoryQuote",
    "HistoryPrint",
    "HistoryFunding",
    "HistoryRate",
    # Auth / subscription
    "LoginResponse",
    "NonceResponse",
    "MeResponse",
    "SubscriptionStatus",
    "RefreshTokenResponse",
    # API keys
    "ApiKey",
    "ApiKeyCreated",
]

_cfg = ConfigDict(populate_by_name=True, extra="allow")


# ── Discovery ─────────────────────────────────────────────────────────────────

class Capabilities(BaseModel):
    model_config = _cfg
    live_quotes: bool = False
    live_prints: bool = False
    live_funding: bool = False
    hist_quotes: bool = False
    hist_prints: bool = False
    hist_funding: bool = False


class MarketStatus(BaseModel):
    model_config = _cfg
    symbols: list[str] = []
    connected: bool = False


MarketsResponse = dict[str, MarketStatus]


class ExchangeSummary(BaseModel):
    model_config = _cfg
    id: str
    live_count: Optional[int] = None
    historical_count: Optional[int] = None
    connected: bool = False
    extensible: bool = False
    capabilities: Optional[Capabilities] = None


class SymbolsResponse(BaseModel):
    model_config = _cfg
    exchanges: list[ExchangeSummary] = []


class ExchangeSymbolsDetail(BaseModel):
    model_config = _cfg
    count: Optional[int] = None
    symbols: list[str] = []
    extensible: bool = False
    note: Optional[str] = None


class ExchangeSymbolsResponse(BaseModel):
    model_config = _cfg
    exchange: str
    connected: bool = False
    capabilities: Optional[Capabilities] = None
    live: Optional[ExchangeSymbolsDetail] = None
    historical: Optional[ExchangeSymbolsDetail] = None


class InstrumentVenue(BaseModel):
    model_config = _cfg
    exchange: str
    symbol: str


class InstrumentVenues(BaseModel):
    model_config = _cfg
    symbol: str
    venues: list[InstrumentVenue] = []


# ── History ───────────────────────────────────────────────────────────────────

class OrderLevel(BaseModel):
    model_config = _cfg
    price: float
    size: float
    fee: Optional[int] = None
    lastSwapMs: Optional[int] = None


class HistoryQuote(BaseModel):
    """One row from GET /v1/history/{exchange}/{symbol}/quotes (5-second sampled)."""
    model_config = _cfg
    type: str = "quote"
    exchange: str
    symbol: str
    bids: list[OrderLevel] = []
    asks: list[OrderLevel] = []
    mid: Optional[float] = None
    time: int


class HistoryPrint(BaseModel):
    """One row from GET /v1/history/{exchange}/{symbol}/trades."""
    model_config = _cfg
    type: str = "print"
    exchange: str
    symbol: str
    price: float
    size: float
    side: int   # 0=sell, 1=buy, 2=unknown
    time: int

    tick: Optional[int] = None
    blockNumber: Optional[int] = None
    txIndex: Optional[int] = None
    logSender: Optional[str] = None


class HistoryFunding(BaseModel):
    """One row from GET /v1/history/{exchange}/{symbol}/funding."""
    model_config = _cfg
    type: str = "funding"
    exchange: str
    symbol: str
    ratePct: float    # annualized percentage
    intervalHrs: int
    time: int


class HistoryRate(BaseModel):
    """One row from GET /v1/history/rates/{address}."""
    model_config = _cfg
    type: str = "rate_market"
    exchange: str
    chain: str
    address: str
    symbol: str
    impliedApy: float
    underlyingApy: Optional[float] = None
    lpApy: Optional[float] = None
    ptPrice: float
    ytPrice: Optional[float] = None
    tvl: float
    volume24h: Optional[float] = None
    tradingFeeRate: Optional[float] = None
    time: int


# ── Auth / Subscription ───────────────────────────────────────────────────────

class LoginResponse(BaseModel):
    model_config = _cfg
    userId: int
    username: str
    token: str


class NonceResponse(BaseModel):
    model_config = _cfg
    nonce: str


class MeResponse(BaseModel):
    model_config = _cfg
    userId: int
    username: str
    role: str
    firmId: Optional[int] = None
    tier: str
    subscriptionExpiry: int   # epoch ms; 0 if unsubscribed


class SubscriptionStatus(BaseModel):
    model_config = _cfg
    tier: str
    expiresAt: Optional[str] = None   # ISO 8601 or null
    active: bool


class RefreshTokenResponse(BaseModel):
    model_config = _cfg
    token: str


# ── API Keys ──────────────────────────────────────────────────────────────────

class ApiKey(BaseModel):
    model_config = _cfg
    id: int
    label: Optional[str] = None
    createdAt: str
    lastUsed: Optional[str] = None


class ApiKeyCreated(ApiKey):
    """Returned once on creation — the raw ``key`` is not stored server-side."""
    key: str   # mk_live_ + 32 hex chars
