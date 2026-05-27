"""Synchronous Mackinac client.

A blocking wrapper around :class:`~mackinac.AsyncClient` for scripts,
notebooks, and any code that doesn't use ``asyncio``.  All I/O runs in a
background daemon thread; the calling thread blocks until each call
completes.

Usage::

    from mackinac import Mackinac, QuoteMessage, PrintMessage

    with Mackinac() as m:
        print(m.live_symbols("hl"))

        with m.subscribe("hl:ETH", types=PrintMessage) as feed:
            for trade in feed:          # plain for loop — no asyncio needed
                print(trade.price, trade.size)
                break

If you are already writing async code, use :class:`~mackinac.AsyncClient`
directly — it has an identical API surface without the threading overhead.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, Iterator, Optional, Union

from ._config import DEFAULT_BASE_URL, DEFAULT_WS_URL
from .client import AsyncClient
from .models.rest import (
    ApiKey,
    ApiKeyCreated,
    HistoryFunding,
    HistoryPrint,
    HistoryQuote,
    HistoryRate,
    InstrumentVenues,
    MarketStatus,
    MeResponse,
    RefreshTokenResponse,
    SubscriptionStatus,
)

__all__ = ["Mackinac"]

# Sentinel used to signal iterator termination across threads
_MISSING = object()


class _SyncFeed:
    """Synchronous iterator over a live subscription stream.

    Obtained via ``with mackinac_client.subscribe(...) as feed``.
    Iterates with a plain ``for`` loop.  Raises on fatal errors (auth
    failure, tier gate).
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        async_feed: Any,
        sync_q: "queue.Queue[Any]",
        sentinel: object,
    ) -> None:
        self._loop = loop
        self._async_feed = async_feed
        self._sync_q = sync_q
        self._sentinel = sentinel

    def __iter__(self) -> Iterator[Any]:
        while True:
            item = self._sync_q.get()
            if item is self._sentinel:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    def unsubscribe(self, *keys: str) -> None:
        """Unsubscribe from one or more ``'exchange:symbol'`` keys."""
        asyncio.run_coroutine_threadsafe(
            self._async_feed.unsubscribe(*keys), self._loop
        ).result(timeout=10)


class _SyncSubscribeCtx:
    """Synchronous context manager returned by :meth:`Mackinac.subscribe`."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        async_client: AsyncClient,
        keys: tuple[str, ...],
        types: Any,
    ) -> None:
        self._loop = loop
        self._async_client = async_client
        self._keys = keys
        self._types = types
        self._async_ctx: Any = None
        self._sync_q: "queue.Queue[Any]" = queue.Queue()
        self._sentinel: object = object()
        self._bridge_task: Optional[asyncio.Task[None]] = None

    def __enter__(self) -> _SyncFeed:
        sentinel = self._sentinel
        sync_q = self._sync_q

        async def _do_enter() -> Any:
            ctx = self._async_client.subscribe(*self._keys, types=self._types)
            self._async_ctx = ctx
            return await ctx.__aenter__()

        async_feed = asyncio.run_coroutine_threadsafe(
            _do_enter(), self._loop
        ).result(timeout=30)

        async def _bridge() -> None:
            try:
                async for msg in async_feed:
                    sync_q.put(msg)
            except Exception as exc:  # noqa: BLE001
                sync_q.put(exc)
            finally:
                sync_q.put(sentinel)

        async def _start_bridge() -> asyncio.Task[None]:
            return asyncio.create_task(_bridge())

        self._bridge_task = asyncio.run_coroutine_threadsafe(
            _start_bridge(), self._loop
        ).result(timeout=5)

        return _SyncFeed(self._loop, async_feed, sync_q, sentinel)

    def __exit__(self, *exc: Any) -> None:
        # Cancel the bridge task so Feed.__anext__ unblocks immediately.
        if self._bridge_task is not None:
            self._loop.call_soon_threadsafe(self._bridge_task.cancel)

        # Close the WS engine.  The websockets connect() uses close_timeout=3 s
        # so this won't block longer than ~3 s even against slow peers.
        if self._async_ctx is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._async_ctx.__aexit__(None, None, None), self._loop
                ).result(timeout=5)
            except Exception:  # noqa: BLE001
                pass

        # Guarantee the sync queue receives the sentinel so __iter__ can return.
        self._sync_q.put(self._sentinel)


class Mackinac:
    """Synchronous client for the Mackinac market-data API.

    A blocking, thread-friendly wrapper around :class:`~mackinac.AsyncClient`.
    All I/O runs in a background daemon thread; call sites need no asyncio::

        with Mackinac() as m:
            print(m.live_symbols("hl"))
            with m.subscribe("hl:ETH", types=PrintMessage) as feed:
                for trade in feed:
                    print(trade.price, trade.size)
                    break

    For async code, use :class:`~mackinac.AsyncClient` directly.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
        _api_key: Optional[str] = None,
        _jwt: Optional[str] = None,
    ) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="mackinac-sync",
        )
        self._thread.start()
        self._ac = AsyncClient(
            base_url=base_url, ws_url=ws_url, _api_key=_api_key, _jwt=_jwt
        )

    # ── Private helper ────────────────────────────────────────────────────────

    def _run(self, coro: Any, timeout: float = 30.0) -> Any:
        """Submit *coro* to the background loop and block until it completes."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def _run_async_gen(self, async_gen: Any) -> Iterator[Any]:
        """Bridge an async generator to a synchronous generator."""
        sync_q: "queue.Queue[Any]" = queue.Queue()
        sentinel = _MISSING

        async def _producer() -> None:
            try:
                async for item in async_gen:
                    sync_q.put(item)
            except Exception as exc:  # noqa: BLE001
                sync_q.put(exc)
            finally:
                sync_q.put(sentinel)

        asyncio.run_coroutine_threadsafe(_producer(), self._loop)

        while True:
            item = sync_q.get()
            if item is sentinel:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_api_key(
        cls,
        key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "Mackinac":
        """Construct a client authenticated with a long-lived API key."""
        return cls(base_url=base_url, ws_url=ws_url, _api_key=key)

    @classmethod
    def from_jwt(
        cls,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "Mackinac":
        """Construct a client authenticated with a JWT (7-day lifetime)."""
        return cls(base_url=base_url, ws_url=ws_url, _jwt=token)

    @classmethod
    def from_token(
        cls,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "Mackinac":
        """Construct from either an API key or a JWT (sniffs ``mk_*`` prefix)."""
        if token.startswith("mk_"):
            return cls.from_api_key(token, base_url=base_url, ws_url=ws_url)
        return cls.from_jwt(token, base_url=base_url, ws_url=ws_url)

    @classmethod
    def from_wallet(
        cls,
        private_key: Union[str, bytes],
        address: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "Mackinac":
        """Authenticate via EIP-191 wallet sign-in (requires ``mackinac-client[wallet]``)."""
        obj = cls.__new__(cls)
        obj._loop = asyncio.new_event_loop()
        obj._thread = threading.Thread(
            target=obj._loop.run_forever,
            daemon=True,
            name="mackinac-sync",
        )
        obj._thread.start()
        obj._ac = obj._run(
            AsyncClient.from_wallet(private_key, address, base_url=base_url, ws_url=ws_url)
        )
        return obj

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the HTTP connection pool and stop the background thread."""
        try:
            self._run(self._ac.aclose(), timeout=10.0)
        except Exception:  # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def __enter__(self) -> "Mackinac":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── Discovery ─────────────────────────────────────────────────────────────

    def markets(self) -> dict[str, MarketStatus]:
        """Return connection status for every venue."""
        return self._run(self._ac.markets())

    def market(self, exchange: str) -> MarketStatus:
        """Return connection status and staleness for a single venue."""
        return self._run(self._ac.market(exchange))

    def live_symbols(
        self, exchange: Optional[str] = None
    ) -> Union[list[str], dict[str, list[str]]]:
        """Return subscribable symbols.

        Args:
            exchange: Venue id (e.g. ``"hl"``).  Omit for all venues.

        Returns:
            ``list[str]`` for a single venue; ``dict[exchange, list[str]]`` for all.
        """
        return self._run(self._ac.live_symbols(exchange))

    def historical_symbols(
        self, exchange: Optional[str] = None
    ) -> Union[list[str], dict[str, list[str]]]:
        """Return symbols that have persisted historical data."""
        return self._run(self._ac.historical_symbols(exchange))

    def instruments(self) -> dict[str, list[str]]:
        """Cross-venue catalog: underlying → list of ``exchange:symbol`` pairs."""
        return self._run(self._ac.instruments())

    def instrument(self, symbol: str) -> InstrumentVenues:
        """Which venues quote a given underlying asset (e.g. ``"ETH"``)."""
        return self._run(self._ac.instrument(symbol))

    # ── Auth / account ────────────────────────────────────────────────────────

    def me(self) -> MeResponse:
        """Return JWT claims for the authenticated user."""
        return self._run(self._ac.me())

    def subscription_status(self) -> SubscriptionStatus:
        """Re-read on-chain subscription state."""
        return self._run(self._ac.subscription_status())

    def refresh_token(self) -> str:
        """Mint a new 7-day JWT; returns the token string."""
        return self._run(self._ac.refresh_token())

    # ── API key management ────────────────────────────────────────────────────

    def create_api_key(self, label: Optional[str] = None) -> ApiKeyCreated:
        """Create a new API key (tier ``api`` or above required)."""
        return self._run(self._ac.create_api_key(label))

    def list_api_keys(self) -> list[ApiKey]:
        """List API key metadata."""
        return self._run(self._ac.list_api_keys())

    def revoke_api_key(self, key_id: int) -> None:
        """Revoke an API key by numeric id."""
        return self._run(self._ac.revoke_api_key(key_id))

    # ── Historical data ───────────────────────────────────────────────────────

    def history_trades(
        self,
        exchange: str,
        symbol: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> Iterator[HistoryPrint]:
        """Iterate over historical trade executions (auto-paginating).

        Free tier: last 1 day only.  Professional/API: up to 90 days.

        Yields:
            :class:`~mackinac.models.rest.HistoryPrint` rows, oldest first.
        """
        yield from self._run_async_gen(
            self._ac.history_trades(exchange, symbol, start=start, end=end, limit=limit)
        )

    def history_quotes(
        self,
        exchange: str,
        symbol: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> Iterator[HistoryQuote]:
        """Iterate over historical 5-second quote snapshots."""
        yield from self._run_async_gen(
            self._ac.history_quotes(exchange, symbol, start=start, end=end, limit=limit)
        )

    def history_funding(
        self,
        exchange: str,
        symbol: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> Iterator[HistoryFunding]:
        """Iterate over historical perpetual funding rate snapshots."""
        yield from self._run_async_gen(
            self._ac.history_funding(exchange, symbol, start=start, end=end, limit=limit)
        )

    def history_rates(
        self,
        address: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> Iterator[HistoryRate]:
        """Iterate over historical yield-market snapshots for a Pendle/Spectra market."""
        yield from self._run_async_gen(
            self._ac.history_rates(address, start=start, end=end, limit=limit)
        )

    # ── WebSocket subscriptions ───────────────────────────────────────────────

    def subscribe(self, *keys: str, types: Any = None) -> _SyncSubscribeCtx:
        """Subscribe to one or more live feed streams.

        Returns a synchronous context manager; iterate with a plain ``for``
        loop inside the ``with`` block::

            with m.subscribe("hl:ETH") as feed:
                for msg in feed:
                    print(msg)
                    break

        Args:
            *keys: One or more ``'exchange:symbol'`` subscription keys.
            types: Optional message-type filter — a class or tuple of classes.
                   Only matching messages are yielded::

                       with m.subscribe("hl:ETH", types=PrintMessage) as feed:
                           for trade in feed:   # every msg is a PrintMessage
                               print(trade.price)

        The connection auto-reconnects on drops.  The ``for`` loop resumes
        seamlessly — no retry logic needed.
        """
        return _SyncSubscribeCtx(self._loop, self._ac, keys, types)
