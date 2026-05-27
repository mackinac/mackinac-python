from __future__ import annotations

__all__ = [
    "MackinacError",
    "AuthError",
    "TierError",
    "RateLimitError",
    "SymbolLimitError",
    "InvalidSymbolError",
    "ServerError",
    "ConnectionError",
]


class MackinacError(Exception):
    """Base class for all mackinac-client errors."""


class AuthError(MackinacError):
    """Authentication failed or credentials expired.

    Raised on HTTP 401, WS ``auth_error`` / ``auth_failed`` frames.
    Not automatically retried — re-authenticate and reconnect.
    """


class TierError(MackinacError):
    """Subscription tier insufficient for the requested resource.

    Raised on HTTP 403, WS ``subscription_required`` frame.
    """


class RateLimitError(MackinacError):
    """Request rate limit exceeded.

    Attributes:
        retry_after: Seconds to wait before retrying (may be None).
    """

    def __init__(self, message: str = "", retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SymbolLimitError(MackinacError):
    """Concurrent symbol cap for your tier has been reached.

    Unsubscribe from a symbol or upgrade your subscription.
    """


class InvalidSymbolError(MackinacError):
    """The requested symbol is unknown on this venue.

    Check ``await client.live_symbols(exchange)`` for valid symbols.
    """


class ServerError(MackinacError):
    """Server-side error (5xx or WS ``internal_error``).

    The request may be retried after a brief backoff.
    """


class ConnectionError(MackinacError):  # noqa: A001 — shadows built-in intentionally
    """Transport-level connection failure."""
