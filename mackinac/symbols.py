"""Symbol name helpers.

Each function documents the naming convention for one venue family and
returns the canonical symbol string the API expects.  Keeping construction
in one place means a single edit if the convention ever changes.
"""
from __future__ import annotations

__all__ = [
    "amm_pair",
    "hl_perp",
    "hl_spot",
    "dydx_perp",
    "gmx_perp",
    "vertex_perp",
    "ostium_pair",
    "pendle_address",
    "spectra_address",
    "rates_all",
    "rates_swaps",
    "rates_market",
]


def amm_pair(base: str, quote: str) -> str:
    """Canonical AMM pair symbol for Uniswap, SushiSwap, PancakeSwap, Balancer.

    Direction matters: ``amm_pair("WETH", "USDC")`` and
    ``amm_pair("USDC", "WETH")`` address different pools.

    >>> amm_pair("WETH", "USDC")
    'WETH/USDC'
    """
    return f"{base}/{quote}"


def hl_perp(asset: str) -> str:
    """Hyperliquid perpetual symbol (bare uppercase ticker).

    Micro-cap assets use a ``k`` prefix (e.g. ``kPEPE``, ``kSHIB``).

    >>> hl_perp("ETH")
    'ETH'
    """
    return asset


def hl_spot(base: str, quote: str = "USDC") -> str:
    """Hyperliquid spot pair (e.g. PURR/USDC).

    >>> hl_spot("PURR")
    'PURR/USDC'
    """
    return f"{base}/{quote}"


def dydx_perp(asset: str) -> str:
    """dYdX V4 perpetual symbol (``BASE-USD``).

    Accepts bare tickers and appends ``-USD``; idempotent on already-canonical
    strings so ``dydx_perp(dydx_perp("ETH")) == "ETH-USD"``.  The backend also
    auto-normalizes bare tickers, so ``dydx:ETH`` would work too — this helper
    just spells the canonical form out.

    >>> dydx_perp("ETH")
    'ETH-USD'
    >>> dydx_perp("BTC-USD")
    'BTC-USD'
    """
    if asset.endswith("-USD") or asset.endswith("-USDC"):
        return asset
    return f"{asset}-USD"


def gmx_perp(asset: str) -> str:
    """GMX perpetual symbol (bare uppercase).

    >>> gmx_perp("ETH")
    'ETH'
    """
    return asset


def vertex_perp(asset: str) -> str:
    """Vertex perpetual symbol (bare uppercase).

    >>> vertex_perp("SOL")
    'SOL'
    """
    return asset


def ostium_pair(base: str, quote: str = "USD") -> str:
    """Ostium RWA pair symbol.

    Crypto assets: ``ostium_pair("ETH")`` → ``'ETH/USD'``.
    Commodities / FX as-is: ``ostium_pair("XAU")`` → ``'XAU/USD'``.
    Index symbols without a quote: pass ``quote=""`` — e.g. ``ostium_pair("SPX", "")`` → ``'SPX'``.

    >>> ostium_pair("XAU")
    'XAU/USD'
    >>> ostium_pair("SPX", "")
    'SPX'
    """
    if quote:
        return f"{base}/{quote}"
    return base


def pendle_address(address: str) -> str:
    """Canonical Pendle market address (lowercased 0x-prefixed).

    Use this as the ``symbol`` when subscribing to a specific Pendle market
    or querying ``/v1/history/rates/{address}``.

    >>> pendle_address("0xC62D75593DAD6C451173553593F86d80Bf29dFe6")
    '0xc62d75593dad6c451173553593f86d80bf29dfe6'
    """
    return address.lower()


def spectra_address(address: str) -> str:
    """Canonical Spectra PT contract address (lowercased 0x-prefixed).

    >>> spectra_address("0xAA8AAD536495FBb96E231099e7D7DED72F25E938")
    '0xaa8aad536495fbb96e231099e7d7ded72f25e938'
    """
    return address.lower()


def rates_all() -> str:
    """Subscribe key for all Pendle + Spectra rate_market messages.

    >>> rates_all()
    'rates:all'
    """
    return "rates:all"


def rates_swaps() -> str:
    """Subscribe key for all Pendle + Spectra trade prints.

    >>> rates_swaps()
    'rates:swaps'
    """
    return "rates:swaps"


def rates_market(pt_symbol_or_address: str) -> str:
    """Subscribe key for a single Pendle/Spectra market by symbol or address.

    >>> rates_market("PT-weETH-25JUN2026")
    'rates:PT-weETH-25JUN2026'
    """
    return f"rates:{pt_symbol_or_address}"
