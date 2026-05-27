"""Pydantic v2 models for all Mackinac API messages.

The primary export is ``FeedMessage`` — a discriminated union of every WebSocket
message type.  Use it with Pydantic's ``TypeAdapter`` to parse raw JSON frames::

    from pydantic import TypeAdapter
    from mackinac.models import FeedMessage

    adapter = TypeAdapter(FeedMessage)
    msg = adapter.validate_python(json.loads(raw_frame))
    if isinstance(msg, PrintMessage):
        print(msg.price, msg.side)
"""
from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field, TypeAdapter

from .messages import (
    AmmBookMessage,
    AmmLiquiditySnapshotMessage,
    ArbFlagMessage,
    AuthedMessage,
    DepthMessage,
    ErrorMessage,
    FeedLiveMessage,
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

__all__ = [
    "FeedMessage",
    # Re-export all message types for convenience
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
]

FeedMessage = Annotated[
    Union[
        SubscribedMessage,
        SnapshotMessage,
        QuoteMessage,
        PrintMessage,
        FundingMessage,
        DepthMessage,
        LiquidityMessage,
        RateMarketMessage,
        RateDepthMessage,
        AmmBookMessage,
        AmmLiquiditySnapshotMessage,
        ArbFlagMessage,
        SpreadMessage,
        FeedStaleMessage,
        FeedLiveMessage,
        ServerClosingMessage,
        AuthedMessage,
        ErrorMessage,
    ],
    Field(discriminator="type"),
]
"""Discriminated union of all WebSocket feed message types.

The ``type`` field is the discriminator.  Pydantic resolves the correct
model at parse time; downstream code can use ``isinstance`` checks or
match-case statements.
"""

_feed_adapter: TypeAdapter[FeedMessage] = TypeAdapter(FeedMessage)
