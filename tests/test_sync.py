"""Unit tests for the synchronous Mackinac wrapper.

Uses mock WS servers (no live network) to verify:
  1. subscribe() delivers messages across thread boundary.
  2. types= filter passes only matching messages.
  3. Symbol limit error is yielded (not raised) as ErrorMessage.
  4. Reconnect — sync iterator continues after a forced disconnect.
  5. history_* generator bridges async gen → sync generator correctly.
"""
import asyncio
import json
import threading

import pytest
from websockets.asyncio.server import serve as ws_serve

from mackinac import Mackinac, PrintMessage, QuoteMessage
from mackinac.models.messages import ErrorMessage
from mackinac._config import DEFAULT_BASE_URL

# ── Shared frame builders ─────────────────────────────────────────────────────

def _quote(exchange: str = "hl", symbol: str = "ETH") -> str:
    return json.dumps({
        "type": "quote", "exchange": exchange, "symbol": symbol,
        "bids": [{"price": 2000.0, "size": 1.0}],
        "asks": [{"price": 2001.0, "size": 1.0}],
        "time": 1748275200000,
    })


def _print_msg(exchange: str = "hl", symbol: str = "ETH", seq: int = 0) -> str:
    """Return a PrintMessage frame.  ``seq`` offsets the timestamp so that
    multiple calls produce distinct dedup keys (the engine deduplicates HL
    prints by exchange/symbol/time/price/size/side)."""
    return json.dumps({
        "type": "print", "exchange": exchange, "symbol": symbol,
        "price": 2000.5, "size": 0.5, "side": 1,
        "time": 1748275200001 + seq,  # unique per call when seq differs
    })


def _limit_error(exchange: str, symbol: str, limit: int = 3) -> str:
    return json.dumps({
        "type": "error", "code": "symbol_limit_reached",
        "exchange": exchange, "symbol": symbol, "limit": limit,
        "message": f"Symbol limit reached ({limit}/{limit})",
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_server_and_test(server_handler, test_fn, timeout=20):
    """Spin up a mock WS server on a background event loop, run test_fn."""
    result_holder = {}
    exc_holder = {}

    def _server_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _run():
            async with ws_serve(server_handler, "localhost", 0) as server:
                port = server.sockets[0].getsockname()[1]
                result_holder["port"] = port
                ready.set()
                await stop_event.wait()

        stop_event = asyncio.Event()
        result_holder["stop"] = lambda: loop.call_soon_threadsafe(stop_event.set)
        loop.run_until_complete(_run())

    ready = threading.Event()
    t = threading.Thread(target=_server_thread, daemon=True)
    t.start()
    ready.wait(timeout=5)

    port = result_holder["port"]
    ws_url = f"ws://localhost:{port}"

    try:
        test_fn(ws_url, result_holder)
    finally:
        result_holder["stop"]()
        t.join(timeout=5)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_sync_subscribe_delivers_messages():
    """Messages cross from the async WS engine to the sync iterator."""
    NUM = 4

    async def _server(ws):
        for _ in range(NUM):
            await ws.send(_quote())
            await asyncio.sleep(0.01)
        await asyncio.sleep(10)  # hold open

    def _test(ws_url, _):
        received = []
        with Mackinac(ws_url=ws_url, base_url=DEFAULT_BASE_URL) as m:
            with m.subscribe("hl:ETH") as feed:
                for msg in feed:
                    received.append(msg)
                    if len(received) >= NUM:
                        break
        assert len(received) == NUM
        assert all(isinstance(m, QuoteMessage) for m in received)

    _run_server_and_test(_server, _test)


def test_sync_types_filter_quotes_only():
    """types=QuoteMessage — PrintMessage frames are silently discarded."""
    async def _server(ws):
        # Interleave: quote, print, quote, print (distinct seq so dedup never triggers)
        for i in range(2):
            await ws.send(_quote())
            await ws.send(_print_msg(seq=i))
            await asyncio.sleep(0.01)
        await asyncio.sleep(10)

    def _test(ws_url, _):
        received = []
        with Mackinac(ws_url=ws_url, base_url=DEFAULT_BASE_URL) as m:
            with m.subscribe("hl:ETH", types=QuoteMessage) as feed:
                for msg in feed:
                    received.append(msg)
                    if len(received) >= 2:
                        break
        assert all(isinstance(m, QuoteMessage) for m in received)
        assert len(received) == 2

    _run_server_and_test(_server, _test)


def test_sync_types_filter_prints_only():
    """types=PrintMessage — QuoteMessage frames are silently discarded."""
    async def _server(ws):
        for i in range(3):
            await ws.send(_quote())          # should be discarded
            await ws.send(_print_msg(seq=i)) # should be yielded; seq keeps dedup keys unique
            await asyncio.sleep(0.01)
        await asyncio.sleep(10)

    def _test(ws_url, _):
        received = []
        with Mackinac(ws_url=ws_url, base_url=DEFAULT_BASE_URL) as m:
            with m.subscribe("hl:ETH", types=PrintMessage) as feed:
                for msg in feed:
                    received.append(msg)
                    if len(received) >= 3:
                        break
        assert all(isinstance(m, PrintMessage) for m in received)
        assert len(received) == 3

    _run_server_and_test(_server, _test)


def test_sync_types_tuple_filter():
    """types=(QuoteMessage, PrintMessage) — yields both, drops everything else."""
    async def _server(ws):
        for i in range(2):
            await ws.send(_quote())
            await ws.send(_print_msg(seq=i))  # distinct seq avoids dedup collisions
            await asyncio.sleep(0.01)
        await asyncio.sleep(10)

    def _test(ws_url, _):
        received = []
        with Mackinac(ws_url=ws_url, base_url=DEFAULT_BASE_URL) as m:
            with m.subscribe("hl:ETH", types=(QuoteMessage, PrintMessage)) as feed:
                for msg in feed:
                    received.append(msg)
                    if len(received) >= 4:
                        break
        assert len(received) == 4
        assert sum(1 for m in received if isinstance(m, QuoteMessage)) == 2
        assert sum(1 for m in received if isinstance(m, PrintMessage)) == 2

    _run_server_and_test(_server, _test)


def test_sync_symbol_limit_yields_error_message():
    """4th subscription gets symbol_limit_reached — yielded as ErrorMessage, not raised."""
    subscribed: set[tuple[str, str]] = set()
    LIMIT = 3

    async def _server(ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("action") != "subscribe":
                continue
            exchange, symbol = msg.get("exchange", ""), msg.get("symbol", "")
            key = (exchange, symbol)
            if key not in subscribed and len(subscribed) < LIMIT:
                subscribed.add(key)
                await ws.send(_quote(exchange, symbol))
            else:
                await ws.send(_limit_error(exchange, symbol, LIMIT))

    def _test(ws_url, _):
        quotes = []
        errors = []
        syms = ["hl:ETH", "hl:BTC", "hl:SOL", "hl:DOGE"]
        with Mackinac(ws_url=ws_url, base_url=DEFAULT_BASE_URL) as m:
            with m.subscribe(*syms) as feed:
                for msg in feed:
                    if isinstance(msg, QuoteMessage):
                        quotes.append(msg)
                    elif isinstance(msg, ErrorMessage):
                        errors.append(msg)
                    if len(quotes) + len(errors) >= LIMIT + 1:
                        break
        assert len(errors) == 1
        assert errors[0].code == "symbol_limit_reached"
        assert errors[0].limit == LIMIT
        assert len(quotes) == LIMIT

    _run_server_and_test(_server, _test)


def test_sync_reconnect_delivers_all_messages():
    """Sync iterator continues across a forced disconnect — same as async test."""
    async def _server(ws):
        for _ in range(3):
            await ws.send(_quote())
            await asyncio.sleep(0.01)
        await ws.close()
        try:
            async for _ in ws:
                pass
        except Exception:
            pass
        for _ in range(3):
            try:
                await ws.send(_quote())
                await asyncio.sleep(0.01)
            except Exception:
                break

    def _test(ws_url, _):
        received = []
        with Mackinac(ws_url=ws_url, base_url=DEFAULT_BASE_URL) as m:
            with m.subscribe("hl:ETH") as feed:
                for msg in feed:
                    received.append(msg)
                    if len(received) >= 6:
                        break
        assert len(received) == 6

    _run_server_and_test(_server, _test)
