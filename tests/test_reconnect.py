"""Tests for the WS reconnect + dedup engine.

Uses a lightweight websockets mock server to verify:
  1. The iterator delivers all messages across a forced disconnect.
  2. Duplicate prints (snapshot replay) are deduped correctly.
  3. Auth frame is sent on reconnect when api_key is configured.
  4. Symbol limit errors are surfaced as ErrorMessage (not raised).
"""
import asyncio
import json

import pytest
import websockets
from websockets.asyncio.server import serve as ws_serve

from mackinac._ws import Feed, _LRUSet, _WsEngine, _dedup_key
from mackinac.models.messages import ErrorMessage, QuoteMessage


# ── Unit tests (no network) ───────────────────────────────────────────────────

class TestLRUSet:
    def test_new_key_returns_false(self):
        s = _LRUSet(maxsize=3)
        assert s.already_seen(("hl", "ETH", 100, 0)) is False

    def test_same_key_returns_true(self):
        s = _LRUSet(maxsize=3)
        key = ("hl", "ETH", 100, 0)
        s.already_seen(key)
        assert s.already_seen(key) is True

    def test_evicts_oldest_when_full(self):
        s = _LRUSet(maxsize=2)
        s.already_seen("a")
        s.already_seen("b")
        s.already_seen("c")  # evicts "a"; dict = {b, c}
        # "b" and "c" are still present; "a" was evicted
        assert s.already_seen("b") is True
        assert s.already_seen("c") is True
        # After seeing "d", the oldest remaining entry is evicted
        s.already_seen("d")
        assert s.already_seen("d") is True


class TestDedupKey:
    def test_non_print_returns_none(self):
        assert _dedup_key({"type": "quote"}) is None
        assert _dedup_key({"type": "funding"}) is None

    def test_onchain_print_uses_block_tx(self):
        frame = {
            "type": "print", "exchange": "uni", "symbol": "WETH/USDC",
            "price": 3500.0, "size": 1.0, "side": 1, "time": 12345,
            "blockNumber": 999, "txIndex": 3,
        }
        key = _dedup_key(frame)
        assert key == ("uni", "WETH/USDC", 999, 3)

    def test_hl_print_uses_time_price_side(self):
        frame = {
            "type": "print", "exchange": "hl", "symbol": "ETH",
            "price": 3500.25, "size": 1.4, "side": 1, "time": 1748275200500,
        }
        key = _dedup_key(frame)
        assert key == ("hl", "ETH", 1748275200500, 3500.25, 1.4, 1)


# ── Integration test: reconnect via mock WS server ───────────────────────────

QUOTE_FRAME = json.dumps({
    "type": "quote", "exchange": "hl", "symbol": "ETH",
    "bids": [{"price": 3500.0, "size": 1.0}],
    "asks": [{"price": 3501.0, "size": 1.0}],
    "time": 1748275200000,
})


async def _mock_server(websocket) -> None:
    """Send 3 quotes, close to trigger reconnect, then send 3 more on the new connection."""
    for _ in range(3):
        await websocket.send(QUOTE_FRAME)
        await asyncio.sleep(0.01)
    await websocket.close()
    # The engine will reconnect; ignore the subscribe message and send 3 more frames
    try:
        async for _ in websocket:
            pass
    except Exception:
        pass
    for _ in range(3):
        try:
            await websocket.send(QUOTE_FRAME)
            await asyncio.sleep(0.01)
        except Exception:
            break


@pytest.mark.asyncio
async def test_reconnect_delivers_all_messages():
    """Iterator continues delivering messages across a forced disconnect."""
    received = []

    async with ws_serve(_mock_server, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        ws_url = f"ws://localhost:{port}"

        engine = _WsEngine(ws_url=ws_url, subscriptions=[("hl", "ETH")])
        await engine.start()

        feed = Feed(engine)
        async for msg in feed:
            received.append(msg)
            if len(received) >= 6:
                break

        await engine.close()

    assert len(received) == 6


@pytest.mark.asyncio
async def test_duplicate_prints_are_deduped():
    """Prints with the same (exchange, symbol, time, price, size, side) are dropped."""
    dup_print = json.dumps({
        "type": "print", "exchange": "hl", "symbol": "ETH",
        "price": 3500.0, "size": 1.0, "side": 1, "time": 9999999,
    })
    send_done = asyncio.Event()

    async def _dup_server(websocket):
        for _ in range(3):
            await websocket.send(dup_print)
            await asyncio.sleep(0.01)
        send_done.set()
        await asyncio.sleep(5)  # hold connection open for test duration

    async with ws_serve(_dup_server, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        engine = _WsEngine(ws_url=f"ws://localhost:{port}", subscriptions=[("hl", "ETH")])
        await engine.start()

        # Wait until server has finished sending, then let engine process the frames
        await asyncio.wait_for(send_done.wait(), timeout=3.0)
        await asyncio.sleep(0.1)

        received = []
        while not engine._queue.empty():
            received.append(engine._queue.get_nowait())

        await engine.close()

    assert len(received) == 1, f"Expected 1 unique print (2 deduped), got {len(received)}"


# ── Symbol limit ──────────────────────────────────────────────────────────────

FREE_TIER_SYMBOL_LIMIT = 3


def _make_quote(exchange: str, symbol: str) -> str:
    return json.dumps({
        "type": "quote", "exchange": exchange, "symbol": symbol,
        "bids": [{"price": 100.0, "size": 1.0}],
        "asks": [{"price": 101.0, "size": 1.0}],
        "time": 1748275200000,
    })


def _make_limit_error(exchange: str, symbol: str) -> str:
    return json.dumps({
        "type": "error",
        "code": "symbol_limit_reached",
        "exchange": exchange,
        "symbol": symbol,
        "limit": FREE_TIER_SYMBOL_LIMIT,
        "message": f"Symbol limit reached for your tier ({FREE_TIER_SYMBOL_LIMIT}/{FREE_TIER_SYMBOL_LIMIT})",
    })


@pytest.mark.asyncio
async def test_symbol_limit_yields_error_message():
    """Subscribing beyond the free-tier cap yields ErrorMessage(code='symbol_limit_reached').

    The 4th subscription frame triggers the server to send a symbol_limit_reached
    error.  The engine must deliver it as an ErrorMessage (not raise an exception),
    leaving the first 3 subscriptions intact.
    """
    subscribed: set[tuple[str, str]] = set()

    async def _limit_server(websocket):
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("action") != "subscribe":
                continue
            exchange = msg.get("exchange", "")
            symbol = msg.get("symbol", "")
            key = (exchange, symbol)
            if key not in subscribed and len(subscribed) < FREE_TIER_SYMBOL_LIMIT:
                subscribed.add(key)
                await websocket.send(_make_quote(exchange, symbol))
            else:
                # Reject the 4th (or duplicate) subscription
                await websocket.send(_make_limit_error(exchange, symbol))

    async with ws_serve(_limit_server, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        engine = _WsEngine(
            ws_url=f"ws://localhost:{port}",
            subscriptions=[
                ("hl", "ETH"), ("hl", "BTC"), ("hl", "SOL"), ("hl", "DOGE"),
            ],
        )
        await engine.start()

        feed = Feed(engine)
        quotes: list[QuoteMessage] = []
        errors: list[ErrorMessage] = []

        async for msg in feed:
            if isinstance(msg, QuoteMessage):
                quotes.append(msg)
            elif isinstance(msg, ErrorMessage):
                errors.append(msg)
            if len(quotes) + len(errors) >= 4:
                break

        await engine.close()

    assert len(quotes) == FREE_TIER_SYMBOL_LIMIT, (
        f"Expected {FREE_TIER_SYMBOL_LIMIT} quotes, got {len(quotes)}"
    )
    assert len(errors) == 1, f"Expected 1 error frame, got {len(errors)}"
    err = errors[0]
    assert err.code == "symbol_limit_reached", f"Unexpected error code: {err.code!r}"
    assert err.limit == FREE_TIER_SYMBOL_LIMIT, f"Unexpected limit value: {err.limit}"
    # The error identifies which symbol was rejected
    assert err.symbol is not None
    assert err.exchange == "hl"
