"""AsyncClient — the main public entry point for the Mackinac data API."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, Optional, Union
from urllib.parse import quote as _urlquote

import httpx

from ._config import (
    DEFAULT_BASE_URL,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_WS_URL,
)
from ._ws import Feed, _SubscribeCtx, _WsEngine
from .exceptions import (
    AuthError,
    InvalidSymbolError,
    RateLimitError,
    ServerError,
    TierError,
)
from .models.rest import (
    ApiKey,
    ApiKeyCreated,
    ExchangeSymbolsResponse,
    HistoryFunding,
    HistoryPrint,
    HistoryQuote,
    HistoryRate,
    InstrumentVenues,
    LoginResponse,
    MarketsResponse,
    MarketStatus,
    MeResponse,
    RefreshTokenResponse,
    SubscriptionStatus,
    SymbolsResponse,
)

__all__ = ["AsyncClient"]


class AsyncClient:
    """Async client for the Mackinac market-data API.

    Instantiate via one of the class-method constructors, then use as an
    async context manager to manage the underlying HTTP connection pool::

        async with AsyncClient.from_api_key("mk_live_...") as client:
            symbols = await client.live_symbols("hl")
            async with client.subscribe("hl:ETH", "uni:WETH/USDC") as feed:
                async for msg in feed:
                    print(msg)

    Anonymous usage (free tier, 3-symbol cap) requires no credentials::

        async with AsyncClient() as client:
            async with client.subscribe("hl:ETH") as feed:
                async for msg in feed:
                    print(msg)
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
        _api_key: Optional[str] = None,
        _jwt: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ws_url = ws_url
        self._api_key = _api_key
        self._jwt = _jwt
        self._http: Optional[httpx.AsyncClient] = None

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_api_key(
        cls,
        key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "AsyncClient":
        """Construct a client authenticated with a long-lived API key.

        API keys (``mk_live_...``) are issued via the dashboard and require
        tier ``api`` or above.  They authenticate WebSocket connections only;
        REST calls are made anonymously unless you also provide a JWT.

        API keys are preferred over JWTs for server-side long-running processes
        because they do not expire.
        """
        return cls(base_url=base_url, ws_url=ws_url, _api_key=key)

    @classmethod
    def from_jwt(
        cls,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "AsyncClient":
        """Construct a client authenticated with a JWT (7-day lifetime).

        JWTs are returned by ``/api/auth/login``, ``/api/auth/register``, and
        ``/api/auth/wallet``.  Use this constructor if you manage token refresh
        yourself, e.g. in a browser context.
        """
        return cls(base_url=base_url, ws_url=ws_url, _jwt=token)

    @classmethod
    def from_token(
        cls,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "AsyncClient":
        """Construct a client from either an API key or a JWT.

        Sniffs the token prefix: ``mk_*`` → API key, anything else → JWT.
        Useful for scripts and examples where the caller has a single credential
        and doesn't want to branch on its type.
        """
        if token.startswith("mk_"):
            return cls.from_api_key(token, base_url=base_url, ws_url=ws_url)
        return cls.from_jwt(token, base_url=base_url, ws_url=ws_url)

    @classmethod
    async def from_wallet(
        cls,
        private_key: Union[str, bytes],
        address: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        ws_url: str = DEFAULT_WS_URL,
    ) -> "AsyncClient":
        """Authenticate via EIP-191 wallet sign-in and return a JWT-backed client.

        Requires ``pip install 'mackinac-client[wallet]'`` (``eth-account``).

        Args:
            private_key: Raw 32-byte private key (bytes) or 0x-prefixed hex string.
            address: Checksummed or lowercase EVM wallet address (0x-prefixed).
        """
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct
        except ImportError as exc:
            raise ImportError(
                "eth-account is required for wallet authentication.\n"
                "Install it with: pip install 'mackinac-client[wallet]'"
            ) from exc

        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=DEFAULT_HTTP_TIMEOUT,
        ) as http:
            r = await http.get("/api/auth/nonce", params={"address": address})
            _raise_for_status(r)
            nonce = r.json()["nonce"]

            msg = encode_defunct(text=f"Sign in to mackinac\nNonce: {nonce}")
            signed = Account.sign_message(msg, private_key=private_key)
            sig: str = signed.signature.hex()
            if not sig.startswith("0x"):
                sig = "0x" + sig

            r2 = await http.post(
                "/api/auth/wallet",
                json={"address": address.lower(), "signature": sig},
            )
            _raise_for_status(r2)
            token = r2.json()["token"]

        return cls(base_url=base_url, ws_url=ws_url, _jwt=token)

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "AsyncClient":
        headers: dict[str, str] = {}
        if self._jwt:
            headers["Authorization"] = f"Bearer {self._jwt}"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=DEFAULT_HTTP_TIMEOUT,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ── Internal HTTP helper ──────────────────────────────────────────────────

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        http = self._ensure_http()
        for attempt in range(DEFAULT_RETRY_ATTEMPTS):
            r = await http.get(path, **kwargs)
            if r.status_code < 500:
                _raise_for_status(r)
                return r
            if attempt < DEFAULT_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(2 ** attempt)
        _raise_for_status(r)
        return r  # unreachable, but satisfies type checker

    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        http = self._ensure_http()
        r = await http.post(path, **kwargs)
        _raise_for_status(r)
        return r

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            # Allow use without async with — create a client on demand
            headers: dict[str, str] = {}
            if self._jwt:
                headers["Authorization"] = f"Bearer {self._jwt}"
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=DEFAULT_HTTP_TIMEOUT,
            )
        return self._http

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def markets(self) -> MarketsResponse:
        """Return connection status for every venue.

        Returns a ``dict[exchange_id, MarketStatus]``.
        """
        r = await self._get("/v1/markets")
        return {k: MarketStatus(**v) for k, v in r.json().items()}

    async def market(self, exchange: str) -> MarketStatus:
        """Return connection status and staleness for a single venue."""
        r = await self._get(f"/v1/markets/{exchange}")
        return MarketStatus(**r.json())

    async def symbols(
        self,
        exchange: Optional[str] = None,
        *,
        kind: Optional[str] = None,
    ) -> Any:
        """Venue symbol catalog.

        Args:
            exchange: Venue id (e.g. ``"hl"``).  Omit to get a summary of all venues.
            kind: ``"live"`` or ``"historical"`` — returns a bare ``list[str]``
                  when combined with ``exchange``.

        Returns:
            - ``SymbolsResponse`` when ``exchange`` is omitted.
            - ``ExchangeSymbolsResponse`` when only ``exchange`` is given.
            - ``list[str]`` when both ``exchange`` and ``kind`` are given.
        """
        if exchange is None:
            r = await self._get("/v1/symbols")
            return SymbolsResponse(**r.json())
        if kind is not None:
            r = await self._get(f"/v1/symbols/{exchange}/{kind}")
            return r.json()  # bare list[str]
        r = await self._get(f"/v1/symbols/{exchange}")
        return ExchangeSymbolsResponse(**r.json())

    async def live_symbols(
        self, exchange: Optional[str] = None
    ) -> Union[list[str], dict[str, list[str]]]:
        """Return subscribable symbols — the most common first call for new users.

        Args:
            exchange: Venue id (e.g. ``"hl"``).  Omit to get all venues.

        Returns:
            ``list[str]`` for a single venue, ``dict[exchange, list[str]]`` for all.

        Examples::

            syms = await client.live_symbols("hl")
            # ['ETH', 'BTC', 'SOL', ...]

            all_syms = await client.live_symbols()
            # {'hl': [...], 'uni': [...], 'pendle': [...], ...}
        """
        if exchange is not None:
            return await self.symbols(exchange, kind="live")  # type: ignore[return-value]

        markets_resp = await self._get("/v1/markets")
        exchanges = list(markets_resp.json().keys())
        result: dict[str, list[str]] = {}
        for ex in exchanges:
            try:
                r = await self._get(f"/v1/symbols/{ex}/live")
                result[ex] = r.json()
            except Exception:
                pass
        return result

    async def historical_symbols(
        self, exchange: Optional[str] = None
    ) -> Union[list[str], dict[str, list[str]]]:
        """Return symbols that have persisted historical data.

        Args:
            exchange: Venue id.  Omit to get all venues.
        """
        if exchange is not None:
            return await self.symbols(exchange, kind="historical")  # type: ignore[return-value]

        markets_resp = await self._get("/v1/markets")
        exchanges = list(markets_resp.json().keys())
        result: dict[str, list[str]] = {}
        for ex in exchanges:
            try:
                r = await self._get(f"/v1/symbols/{ex}/historical")
                result[ex] = r.json()
            except Exception:
                pass
        return result

    async def instruments(self) -> dict[str, list[str]]:
        """Cross-venue catalog: underlying symbol → list of ``exchange:symbol`` pairs."""
        r = await self._get("/v1/instruments")
        return r.json()

    async def instrument(self, symbol: str) -> InstrumentVenues:
        """Which venues quote a given underlying asset (e.g. ``"ETH"``)."""
        r = await self._get(f"/v1/instruments/{symbol}")
        return InstrumentVenues(**r.json())

    # ── Auth / account ────────────────────────────────────────────────────────

    async def me(self) -> MeResponse:
        """Return the JWT claims for the authenticated user."""
        r = await self._get("/api/auth/me")
        return MeResponse(**r.json())

    async def subscription_status(self) -> SubscriptionStatus:
        """Re-read on-chain subscription state and return current tier/expiry."""
        r = await self._get("/api/subscription/status")
        return SubscriptionStatus(**r.json())

    async def refresh_token(self) -> str:
        """Mint a new 7-day JWT with updated on-chain tier claims.

        Returns the new token string.  Update your stored JWT and recreate
        the client (``AsyncClient.from_jwt(new_token)``) if needed.
        """
        r = await self._post("/api/subscription/refresh-token")
        return RefreshTokenResponse(**r.json()).token

    # ── API key management ────────────────────────────────────────────────────

    async def create_api_key(self, label: Optional[str] = None) -> ApiKeyCreated:
        """Create a new API key (requires tier ``api`` or above).

        The raw key is returned ONCE — store it immediately.
        """
        payload: dict[str, Any] = {}
        if label is not None:
            payload["label"] = label
        r = await self._post("/api/apikeys", json=payload)
        return ApiKeyCreated(**r.json())

    async def list_api_keys(self) -> list[ApiKey]:
        """List your API keys (metadata only — raw keys are not stored server-side)."""
        r = await self._get("/api/apikeys")
        return [ApiKey(**k) for k in r.json()]

    async def revoke_api_key(self, key_id: int) -> None:
        """Revoke an API key by its numeric id."""
        http = self._ensure_http()
        r = await http.delete(f"/api/apikeys/{key_id}")
        _raise_for_status(r)

    # ── Historical data ───────────────────────────────────────────────────────

    async def history_trades(
        self,
        exchange: str,
        symbol: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> AsyncGenerator[HistoryPrint, None]:
        """Iterate over historical trade executions.

        Args:
            exchange: Venue id (e.g. ``"hl"``, ``"uni"``, ``"ostium"``).
            symbol: Symbol on that venue (e.g. ``"ETH"``, ``"WETH/USDC"``).
            start: Start of range — ISO 8601 string or epoch milliseconds.
                   Defaults to 24 hours ago.
            end: End of range.  Defaults to now.
            limit: Rows per page (1–10 000).

        Yields:
            :class:`~mackinac.models.rest.HistoryPrint` rows, oldest first.

        Example::

            async for trade in client.history_trades("hl", "ETH",
                                                      start="2026-04-01",
                                                      end="2026-04-08"):
                print(trade.price, trade.size, trade.side)
        """
        async for row in self._history_iter(
            f"/v1/history/{exchange}/{_urlquote(symbol, safe='')}/trades",
            start=start, end=end, limit=limit,
        ):
            yield HistoryPrint(**row)

    async def history_quotes(
        self,
        exchange: str,
        symbol: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> AsyncGenerator[HistoryQuote, None]:
        """Iterate over historical 5-second quote snapshots."""
        async for row in self._history_iter(
            f"/v1/history/{exchange}/{_urlquote(symbol, safe='')}/quotes",
            start=start, end=end, limit=limit,
        ):
            yield HistoryQuote(**row)

    async def history_funding(
        self,
        exchange: str,
        symbol: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> AsyncGenerator[HistoryFunding, None]:
        """Iterate over historical perpetual funding rate snapshots."""
        async for row in self._history_iter(
            f"/v1/history/{exchange}/{_urlquote(symbol, safe='')}/funding",
            start=start, end=end, limit=limit,
        ):
            yield HistoryFunding(**row)

    async def history_rates(
        self,
        address: str,
        *,
        start: Optional[Union[str, int]] = None,
        end: Optional[Union[str, int]] = None,
        limit: int = 1_000,
    ) -> AsyncGenerator[HistoryRate, None]:
        """Iterate over historical yield-market snapshots for a Pendle/Spectra market.

        Args:
            address: Market contract address (lowercase 0x-prefixed).
                     Use ``mackinac.symbols.pendle_address(addr)`` to normalize.
        """
        async for row in self._history_iter(
            f"/v1/history/rates/{address}",
            start=start, end=end, limit=limit,
        ):
            yield HistoryRate(**row)

    async def _history_iter(
        self,
        path: str,
        *,
        start: Optional[Union[str, int]],
        end: Optional[Union[str, int]],
        limit: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Paginate a history endpoint, yielding raw row dicts."""
        params: dict[str, Any] = {"limit": limit}
        if start is not None:
            params["from"] = start
        if end is not None:
            params["to"] = end

        while True:
            r = await self._get(path, params=params)
            body = r.json()
            for row in body.get("data", []):
                yield row
            cursor = body.get("next_cursor")
            if not cursor:
                break
            params = {"limit": limit, "cursor": cursor}

    # ── WebSocket subscriptions ───────────────────────────────────────────────

    def subscribe(self, *keys: str, types: Any = None) -> _SubscribeCtx:
        """Subscribe to one or more live feed streams.

        Each key is an ``'exchange:symbol'`` string.  Special keys for
        consolidated feeds: ``'rates:all'``, ``'rates:swaps'``,
        ``'ammbook:WETH/USDC'``.

        Args:
            *keys: One or more ``'exchange:symbol'`` subscription keys.
            types: Optional message-type filter.  Pass a single class or a
                   tuple of classes; only messages of those types will be
                   yielded.  Non-matching messages are consumed and discarded.

                   Examples::

                       # Only trade prints — no isinstance check needed
                       async with client.subscribe("hl:ETH", types=PrintMessage) as feed:
                           async for trade in feed:
                               print(trade.price, trade.size)

                       # Quotes and prints together
                       async with client.subscribe("hl:ETH",
                                                   types=(QuoteMessage, PrintMessage)) as feed:
                           async for msg in feed:
                               ...

                       # All types (default)
                       async with client.subscribe("hl:ETH") as feed:
                           async for msg in feed:
                               ...

        Returns an async context manager.  The connection auto-reconnects on
        drops with exponential backoff (1s → 2s → 4s → … → 30s cap).
        """
        subs = _parse_keys(keys)
        engine = _WsEngine(
            ws_url=self._ws_url,
            subscriptions=subs,
            api_key=self._api_key,
            jwt=self._jwt,
        )
        return _SubscribeCtx(engine, types=types)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _parse_keys(keys: tuple[str, ...]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for key in keys:
        if ":" not in key:
            raise ValueError(
                f"Subscribe key must be 'exchange:symbol' (e.g. 'hl:ETH'), got: {key!r}"
            )
        exchange, symbol = key.split(":", 1)
        result.append((exchange, symbol))
    return result


def _raise_for_status(r: httpx.Response) -> None:
    if r.status_code == 200:
        return
    try:
        body = r.json()
    except Exception:
        body = {}

    msg = body.get("message") or body.get("error") or r.text or ""
    code = r.status_code

    if code == 401:
        raise AuthError(msg)
    if code == 403:
        raise TierError(msg)
    if code == 404:
        raise InvalidSymbolError(msg)
    if code == 429:
        retry = None
        try:
            retry = int(r.headers.get("retry-after") or body.get("retryAfter") or 0) or None
        except (ValueError, TypeError):
            pass
        raise RateLimitError(msg, retry_after=retry)
    if code >= 500:
        raise ServerError(f"HTTP {code}: {msg}")
    r.raise_for_status()
