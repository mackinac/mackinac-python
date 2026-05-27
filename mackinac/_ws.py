"""Internal WebSocket engine.

Handles connection lifecycle, auth, subscriptions, dedup, backpressure,
and automatic reconnect with exponential backoff.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict, deque
from typing import Any, Optional

import websockets
import websockets.exceptions

from .exceptions import AuthError, TierError
from .models import FeedMessage, _feed_adapter

_logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

class _LRUSet:
    """Fixed-size ordered set for print deduplication."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self._d: OrderedDict[Any, None] = OrderedDict()
        self._maxsize = maxsize

    def already_seen(self, key: Any) -> bool:
        if key in self._d:
            self._d.move_to_end(key)
            return True
        self._d[key] = None
        if len(self._d) > self._maxsize:
            self._d.popitem(last=False)
        return False


class _SubscribeThrottle:
    """Sliding-window rate limiter: 30 subscribe actions per 10-second window."""

    def __init__(self, limit: int = 30, window: float = 10.0) -> None:
        self._limit = limit
        self._window = window
        self._ts: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            while self._ts and now - self._ts[0] > self._window:
                self._ts.popleft()
            if len(self._ts) < self._limit:
                self._ts.append(now)
                return
            sleep_s = self._window - (now - self._ts[0]) + 0.05
            await asyncio.sleep(sleep_s)


def _dedup_key(msg: dict[str, Any]) -> Optional[tuple]:
    """Return a dedup key for PrintMessage frames; None for all other types.

    On-chain venues: deduplicated by (exchange, symbol, blockNumber, txIndex).
    HL (no blockNumber): deduplicated by (exchange, symbol, time, price, size, side).
    """
    if msg.get("type") != "print":
        return None
    exchange = msg.get("exchange", "hl")
    block = msg.get("blockNumber")
    tx = msg.get("txIndex")
    sym = msg.get("symbol")
    if block is not None and tx is not None:
        return (exchange, sym, block, tx)
    return (exchange, sym, msg.get("time"), msg.get("price"), msg.get("size"), msg.get("side"))


# ── Public API ─────────────────────────────────────────────────────────────────

class Feed:
    """Async iterator over a live WebSocket subscription stream.

    Obtained via ``async with client.subscribe(...) as feed``.
    Yields typed ``FeedMessage`` instances; raises on fatal errors (auth
    failure, tier gate).

    Call ``await feed.unsubscribe("exchange:symbol")`` to remove individual
    subscriptions without closing the connection.

    If ``types`` was passed to ``subscribe()``, only messages whose type
    matches are yielded — non-matching messages are silently consumed.
    """

    def __init__(
        self,
        engine: _WsEngine,
        types: Optional[Any] = None,  # type | tuple[type, ...] | None
    ) -> None:
        self._engine = engine
        # Normalise to a tuple so isinstance() always works
        if types is None:
            self._types: Optional[tuple[type, ...]] = None
        elif isinstance(types, tuple):
            self._types = types
        else:
            self._types = (types,)

    def __aiter__(self) -> Feed:
        return self

    async def __anext__(self) -> FeedMessage:
        while True:
            if self._engine._fatal_error is not None:
                raise self._engine._fatal_error
            item = await self._engine._queue.get()
            if isinstance(item, BaseException):
                raise item
            # type filter — skip non-matching messages
            if self._types is not None and not isinstance(item, self._types):
                continue
            return item  # type: ignore[return-value]

    async def unsubscribe(self, *keys: str) -> None:
        """Unsubscribe from one or more ``'exchange:symbol'`` keys."""
        for key in keys:
            if ":" not in key:
                raise ValueError(f"key must be 'exchange:symbol', got: {key!r}")
            exchange, symbol = key.split(":", 1)
            await self._engine._remove_sub(exchange, symbol)


class _SubscribeCtx:
    """Async context manager returned by ``AsyncClient.subscribe()``."""

    def __init__(self, engine: _WsEngine, types: Optional[Any] = None) -> None:
        self._engine = engine
        self._types = types

    async def __aenter__(self) -> Feed:
        await self._engine.start()
        return Feed(self._engine, types=self._types)

    async def __aexit__(self, *exc: Any) -> None:
        await self._engine.close()


class _WsEngine:
    def __init__(
        self,
        ws_url: str,
        subscriptions: list[tuple[str, str]],
        api_key: Optional[str] = None,
        jwt: Optional[str] = None,
    ) -> None:
        self._ws_url = ws_url
        self._active_subs: set[tuple[str, str]] = set(subscriptions)
        self._api_key = api_key
        self._jwt = jwt

        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=10_000)
        self._seen = _LRUSet()
        self._throttle = _SubscribeThrottle()

        self._task: Optional[asyncio.Task[None]] = None
        self._closed = False
        self._fatal_error: Optional[BaseException] = None
        self._pending_reconnect_ms: Optional[int] = None
        self._ws: Any = None  # active websockets connection

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="mackinac-ws")

    async def close(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._ws = None

    async def _remove_sub(self, exchange: str, symbol: str) -> None:
        self._active_subs.discard((exchange, symbol))
        if self._ws is not None:
            try:
                await self._ws.send(
                    json.dumps({"action": "unsubscribe", "exchange": exchange, "symbol": symbol})
                )
            except Exception:
                pass

    async def _run(self) -> None:
        backoff = 1.0
        while not self._closed:
            if self._pending_reconnect_ms is not None:
                wait_s = self._pending_reconnect_ms / 1000.0
                self._pending_reconnect_ms = None
                _logger.debug("mackinac ws: server requested %.1fs reconnect delay", wait_s)
                await asyncio.sleep(wait_s)

            try:
                await self._connect_and_run()
                backoff = 1.0
            except (AuthError, TierError) as exc:
                self._fatal_error = exc
                return
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if self._closed:
                    return
                _logger.debug("mackinac ws: disconnected (%s), retry in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _connect_and_run(self) -> None:
        async with websockets.connect(
            self._ws_url,
            ping_interval=20,
            ping_timeout=10,
            open_timeout=15,
            close_timeout=3,
            max_size=10 * 1024 * 1024,  # 10 MB — HL full book snapshots can exceed 1 MB
        ) as ws:
            self._ws = ws
            jwt_sent = False

            # Authenticate with API key (recommended for servers)
            if self._api_key:
                await ws.send(json.dumps({"action": "auth", "key": self._api_key}))
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                except asyncio.TimeoutError:
                    raise AuthError("timed out waiting for authed frame")
                frame = json.loads(raw)
                if frame.get("type") == "error":
                    raise AuthError(frame.get("message", "authentication failed"))

            # Subscribe to all active symbols
            for exchange, symbol in list(self._active_subs):
                await self._throttle.acquire()
                msg: dict[str, Any] = {
                    "action": "subscribe",
                    "exchange": exchange,
                    "symbol": symbol,
                }
                # Include JWT on first subscribe of this session (browser-style auth)
                if not jwt_sent and self._jwt and not self._api_key:
                    msg["token"] = self._jwt
                    jwt_sent = True
                await ws.send(json.dumps(msg))

            # Request recent-print history for each symbol.  The server sends back a
            # SnapshotMessage with the ring-buffer contents (oldest-first).  Subscribe
            # no longer auto-delivers this blob, so we ask for it explicitly — same
            # pattern as the frontend.
            for exchange, symbol in list(self._active_subs):
                await ws.send(json.dumps({
                    "action": "history",
                    "exchange": exchange,
                    "symbol": symbol,
                }))

            # Message loop
            async for raw in ws:
                if self._closed:
                    return

                try:
                    frame = json.loads(raw)
                except Exception:
                    continue

                msg_type = frame.get("type")

                if msg_type == "server_closing":
                    self._pending_reconnect_ms = frame.get("reconnectIn", 5_000)
                    return

                if msg_type == "error":
                    code = frame.get("code", "")
                    if code in ("auth_error", "auth_failed"):
                        raise AuthError(frame.get("message", "authentication failed"))
                    if code == "subscription_required":
                        raise TierError(frame.get("message", "professional tier required"))
                    # Permanently rejected symbols — drop from active_subs so that
                    # reconnects don't re-subscribe them and trigger the error again.
                    if code in ("symbol_limit_reached", "invalid_symbol", "unknown_symbol"):
                        exc = frame.get("exchange")
                        sym = frame.get("symbol")
                        if exc and sym:
                            self._active_subs.discard((exc, sym))
                    # Other WS errors — parse and deliver as ErrorMessage so the caller
                    # can handle them.

                # Dedup print messages after reconnect snapshot replay
                if msg_type == "print":
                    key = _dedup_key(frame)
                    if key is not None and self._seen.already_seen(key):
                        continue

                try:
                    typed = _feed_adapter.validate_python(frame)
                except Exception:
                    continue  # skip malformed frames

                # Backpressure: drop oldest if queue is full
                if self._queue.full():
                    try:
                        self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    _logger.warning(
                        "mackinac: output queue full; dropping oldest message. "
                        "Process messages faster or reduce subscription count."
                    )

                self._queue.put_nowait(typed)

        self._ws = None
