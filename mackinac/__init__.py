"""mackinac-client — Python client for the Mackinac market-data API.

Synchronous quick start (no asyncio required)::

    from mackinac import Mackinac, PrintMessage

    with Mackinac() as m:
        print(m.live_symbols("hl")[:5])

        with m.subscribe("hl:ETH", types=PrintMessage) as feed:
            for trade in feed:
                print(trade.price, trade.size)
                break

Async quick start::

    import asyncio
    from mackinac import AsyncClient

    async def main():
        async with AsyncClient() as client:
            syms = await client.live_symbols("hl")
            async with client.subscribe("hl:ETH") as feed:
                async for msg in feed:
                    print(msg); break

    asyncio.run(main())
"""
from __future__ import annotations

from .client import AsyncClient
from .sync import Mackinac
from .exceptions import (
    AuthError,
    ConnectionError,
    InvalidSymbolError,
    MackinacError,
    RateLimitError,
    ServerError,
    SymbolLimitError,
    TierError,
)
from .models import (
    AmmBookMessage,
    AmmLiquiditySnapshotMessage,
    ArbFlagMessage,
    AuthedMessage,
    DepthMessage,
    ErrorMessage,
    FeedLiveMessage,
    FeedMessage,
    FeedStaleMessage,
    FundingMessage,
    LiquidityMessage,
    PrintMessage,
    QuoteMessage,
    RateDepthMessage,
    RateMarketMessage,
    ServerClosingMessage,
    SnapshotMessage,
    SpreadMessage,
    SubscribedMessage,
)
from . import symbols

__version__ = "0.1.0"
__protocol_version__ = "1.0.0"

__all__ = [
    # Clients
    "AsyncClient",
    "Mackinac",
    # Exceptions
    "MackinacError",
    "AuthError",
    "TierError",
    "RateLimitError",
    "SymbolLimitError",
    "InvalidSymbolError",
    "ServerError",
    "ConnectionError",
    # Message types
    "FeedMessage",
    "SubscribedMessage",
    "SnapshotMessage",
    "QuoteMessage",
    "PrintMessage",
    "FundingMessage",
    "DepthMessage",
    "LiquidityMessage",
    "RateMarketMessage",
    "RateDepthMessage",
    "AmmBookMessage",
    "AmmLiquiditySnapshotMessage",
    "ArbFlagMessage",
    "SpreadMessage",
    "FeedStaleMessage",
    "FeedLiveMessage",
    "ServerClosingMessage",
    "AuthedMessage",
    "ErrorMessage",
    # Symbol helpers module
    "symbols",
    # Version
    "__version__",
    "__protocol_version__",
]
