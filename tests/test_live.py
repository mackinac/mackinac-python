"""Integration tests against a live Mackinac server.

Run against dev (default):
    pytest -m live -v

Run against production:
    pytest -m live -v --server=prod

These tests require the backend to be reachable and are skipped in normal CI.
They verify real server behaviour — not just that the library handles frames
correctly, but that the server enforces the documented contracts.
"""
import asyncio
import os

import pytest

from mackinac import AsyncClient
from mackinac.models.messages import ErrorMessage, QuoteMessage

pytestmark = pytest.mark.live


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def live_urls(request: pytest.FixtureRequest) -> tuple[str, str]:
    """Return (base_url, ws_url) for the target server (dev or prod)."""
    from conftest import SERVERS
    server = request.config.getoption("--server")
    return SERVERS[server]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client(live_urls: tuple[str, str]) -> AsyncClient:
    """Auth-aware client.  Uses MACKINAC_TOKEN (API key) if set, else anonymous.

    Most subscribe tests don't intrinsically need auth — they need the IP-wide
    anonymous symbol cap NOT to be saturated.  Setting MACKINAC_TOKEN bypasses
    the cap so the suite can run when other anonymous sessions are active.
    """
    base_url, ws_url = live_urls
    token = os.getenv("MACKINAC_TOKEN")
    if token:
        return AsyncClient.from_api_key(token, base_url=base_url, ws_url=ws_url)
    return AsyncClient(base_url=base_url, ws_url=ws_url)


def _anonymous_client(live_urls: tuple[str, str]) -> AsyncClient:
    """Force anonymous (no auth) — for tests that verify free-tier behaviour."""
    base_url, ws_url = live_urls
    return AsyncClient(base_url=base_url, ws_url=ws_url)


def _sync_client(live_urls: tuple[str, str]):
    from mackinac import Mackinac
    base_url, ws_url = live_urls
    token = os.getenv("MACKINAC_TOKEN")
    if token:
        return Mackinac.from_api_key(token, base_url=base_url, ws_url=ws_url)
    return Mackinac(base_url=base_url, ws_url=ws_url)


def _anonymous_sync_client(live_urls: tuple[str, str]):
    from mackinac import Mackinac
    base_url, ws_url = live_urls
    return Mackinac(base_url=base_url, ws_url=ws_url)


# ── REST ──────────────────────────────────────────────────────────────────────

async def test_live_markets(live_urls: tuple[str, str]):
    """GET /v1/markets returns a non-empty dict with known venues."""
    async with _client(live_urls) as c:
        markets = await c.markets()
    assert "hl" in markets
    assert "ostium" in markets
    assert markets["hl"].connected is True


async def test_live_live_symbols_single_venue(live_urls: tuple[str, str]):
    """live_symbols('hl') returns a non-empty list of strings."""
    async with _client(live_urls) as c:
        syms = await c.live_symbols("hl")
    assert isinstance(syms, list)
    assert len(syms) > 0
    assert "ETH" in syms


async def test_live_live_symbols_all_venues(live_urls: tuple[str, str]):
    """live_symbols() returns a dict keyed by exchange name."""
    async with _client(live_urls) as c:
        all_syms = await c.live_symbols()
    assert isinstance(all_syms, dict)
    assert "hl" in all_syms
    assert "pendle" in all_syms


async def test_live_historical_symbols(live_urls: tuple[str, str]):
    """historical_symbols('hl') returns a non-empty list."""
    async with _client(live_urls) as c:
        syms = await c.historical_symbols("hl")
    assert isinstance(syms, list)
    assert len(syms) > 0


# ── WebSocket — basic subscription ───────────────────────────────────────────

async def test_live_subscribe_single(live_urls: tuple[str, str]):
    """Subscribe to hl:ETH and receive at least one QuoteMessage."""
    async with _client(live_urls) as c:
        async with c.subscribe("hl:ETH") as feed:
            async for msg in feed:
                if isinstance(msg, QuoteMessage):
                    assert msg.exchange == "hl"
                    assert msg.symbol == "ETH"
                    assert isinstance(msg.time, int)
                    break


async def test_live_subscribe_rates(live_urls: tuple[str, str]):
    """Subscribe to rates:all and receive at least one RateMarketMessage."""
    from mackinac.models.messages import RateMarketMessage
    async with _client(live_urls) as c:
        async with c.subscribe("rates:all") as feed:
            async for msg in feed:
                if isinstance(msg, RateMarketMessage):
                    assert msg.impliedApy is not None
                    break


# ── WebSocket — symbol limit enforcement ──────────────────────────────────────

FREE_TIER_LIMIT = 3


async def test_live_symbol_limit_enforced(live_urls: tuple[str, str]):
    """Subscribing to a 4th symbol as an anonymous user yields ErrorMessage(code='symbol_limit_reached').

    The server enforces a 3-symbol cap per session for unauthenticated (free-tier)
    users.  The 4th subscribe frame must trigger an error frame — not a crash,
    not a silent drop — and the iterator must surface it as a typed ErrorMessage.
    The first 3 subscriptions remain live.
    """
    symbols = ["hl:ETH", "hl:BTC", "hl:SOL", "hl:DOGE"]  # 4 — one over the limit

    # Acceptable cap-protection codes:
    #   symbol_limit_reached  — per-session cap (fresh anonymous session)
    #   free_tier_cap_reached — per-IP cap (other anonymous sessions active on same IP)
    cap_codes = {"symbol_limit_reached", "free_tier_cap_reached"}

    async with _anonymous_client(live_urls) as c:
        async with c.subscribe(*symbols) as feed:
            quotes: list[QuoteMessage] = []
            errors: list[ErrorMessage] = []

            async for msg in feed:
                if isinstance(msg, QuoteMessage):
                    quotes.append(msg)
                elif isinstance(msg, ErrorMessage):
                    errors.append(msg)

                if len(quotes) + len(errors) >= len(symbols):
                    break

    assert errors, "Expected at least one cap error, got none"
    err_codes = {e.code for e in errors}
    assert err_codes <= cap_codes, f"Unexpected error codes: {err_codes - cap_codes}"
    assert all(e.exchange == "hl" for e in errors)
    assert all(e.symbol in {"ETH", "BTC", "SOL", "DOGE"} for e in errors)


async def test_live_history_gated_for_anonymous(live_urls: tuple[str, str]):
    """Requesting history older than 1 day raises TierError for anonymous users."""
    from mackinac.exceptions import TierError
    async with _anonymous_client(live_urls) as c:
        with pytest.raises(TierError):
            async for _ in c.history_trades("hl", "ETH", start="2026-05-20", end="2026-05-21"):
                break


# ── Sync (Mackinac) live tests ────────────────────────────────────────────────

def test_live_sync_markets(live_urls: tuple[str, str]):
    """Mackinac.markets() returns a non-empty dict with known venues."""
    with _sync_client(live_urls) as m:
        markets = m.markets()
    assert "hl" in markets
    assert markets["hl"].connected is True


def test_live_sync_live_symbols(live_urls: tuple[str, str]):
    """Mackinac.live_symbols('hl') returns ETH in the symbol list."""
    with _sync_client(live_urls) as m:
        syms = m.live_symbols("hl")
    assert "ETH" in syms


def test_live_sync_subscribe_quote(live_urls: tuple[str, str]):
    """Mackinac.subscribe with types=QuoteMessage — first message is a QuoteMessage."""
    from mackinac import QuoteMessage
    with _sync_client(live_urls) as m:
        with m.subscribe("hl:ETH", types=QuoteMessage) as feed:
            for msg in feed:
                assert isinstance(msg, QuoteMessage)
                assert msg.exchange == "hl"
                break


def test_live_sync_subscribe_print(live_urls: tuple[str, str]):
    """Mackinac.subscribe with types=PrintMessage — first message is a PrintMessage."""
    from mackinac import PrintMessage
    with _sync_client(live_urls) as m:
        with m.subscribe("hl:ETH", types=PrintMessage) as feed:
            for msg in feed:
                assert isinstance(msg, PrintMessage)
                assert msg.exchange == "hl"
                break


def test_live_sync_symbol_limit_enforced(live_urls: tuple[str, str]):
    """Sync client: 4th subscription yields ErrorMessage(code='symbol_limit_reached')."""
    from mackinac import Mackinac, QuoteMessage
    from mackinac.models.messages import ErrorMessage

    symbols = ["hl:ETH", "hl:BTC", "hl:SOL", "hl:DOGE"]
    cap_codes = {"symbol_limit_reached", "free_tier_cap_reached"}
    with _anonymous_sync_client(live_urls) as m:
        with m.subscribe(*symbols) as feed:
            quotes = []
            errors = []
            for msg in feed:
                if isinstance(msg, QuoteMessage):
                    quotes.append(msg)
                elif isinstance(msg, ErrorMessage):
                    errors.append(msg)
                if len(quotes) + len(errors) >= len(symbols):
                    break

    assert errors, "Expected at least one cap error"
    assert {e.code for e in errors} <= cap_codes


def test_live_sync_history_gated_for_anonymous(live_urls: tuple[str, str]):
    """Mackinac: history older than 1 day raises TierError for anonymous users."""
    from mackinac.exceptions import TierError
    with _anonymous_sync_client(live_urls) as m:
        with pytest.raises(TierError):
            for _ in m.history_trades("hl", "ETH", start="2026-05-20", end="2026-05-21"):
                break
