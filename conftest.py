"""Shared pytest configuration and fixtures."""
from __future__ import annotations

SERVERS = {
    "dev":  ("http://192.168.50.61:3001",   "ws://192.168.50.61:3001/feed"),
    "prod": ("https://api.mackinac.io",      "wss://api.mackinac.io/feed"),
}


def pytest_addoption(parser: object) -> None:
    parser.addoption(  # type: ignore[attr-defined]
        "--server",
        default="dev",
        choices=list(SERVERS),
        help="Live-test target: 'dev' (192.168.50.61) or 'prod' (api.mackinac.io)",
    )


def pytest_configure(config: object) -> None:  # type: ignore[override]
    """Register the 'live' marker so -m live works without warnings."""
    config.addinivalue_line(  # type: ignore[attr-defined]
        "markers",
        "live: integration tests that require a live Mackinac server (run with -m live)",
    )
