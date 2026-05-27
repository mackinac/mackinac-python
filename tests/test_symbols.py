"""Tests for mackinac.symbols helper functions."""
import pytest

from mackinac import symbols


@pytest.mark.parametrize("base,quote,expected", [
    ("WETH", "USDC",  "WETH/USDC"),
    ("WBTC", "WETH",  "WBTC/WETH"),
    ("USDC", "WETH",  "USDC/WETH"),
])
def test_amm_pair(base, quote, expected):
    assert symbols.amm_pair(base, quote) == expected


def test_hl_perp():
    assert symbols.hl_perp("ETH") == "ETH"
    assert symbols.hl_perp("kPEPE") == "kPEPE"


def test_hl_spot():
    assert symbols.hl_spot("PURR") == "PURR/USDC"
    assert symbols.hl_spot("HFUN", "USDC") == "HFUN/USDC"


def test_ostium_pair():
    assert symbols.ostium_pair("XAU") == "XAU/USD"
    assert symbols.ostium_pair("ETH") == "ETH/USD"
    assert symbols.ostium_pair("SPX", "") == "SPX"
    assert symbols.ostium_pair("EUR", "USD") == "EUR/USD"


def test_pendle_address_normalises():
    raw = "0xC62D75593DAD6C451173553593F86d80Bf29dFe6"
    assert symbols.pendle_address(raw) == raw.lower()
    assert symbols.pendle_address(raw.lower()) == raw.lower()


def test_spectra_address_normalises():
    raw = "0xAA8AAD536495FBb96E231099e7D7DED72F25E938"
    assert symbols.spectra_address(raw) == raw.lower()


def test_rates_keys():
    assert symbols.rates_all() == "rates:all"
    assert symbols.rates_swaps() == "rates:swaps"
    assert symbols.rates_market("PT-weETH-25JUN2026") == "rates:PT-weETH-25JUN2026"
    assert symbols.rates_market("0xabc123") == "rates:0xabc123"
