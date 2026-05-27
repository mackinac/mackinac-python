"""yield_rates.py — subscribe to all Pendle + Spectra rate markets and display
a live table sorted by implied APY.

Demonstrates:
  - rates:all subscription (both Pendle and Spectra)
  - RateMarketMessage field semantics
  - Venue-specific quirks: Pendle uses USD TVL; Spectra v1 uses asset-unit TVL

Run:
    python examples/yield_rates.py
"""
import asyncio
import os
from datetime import datetime, timezone

from mackinac import AsyncClient, RateMarketMessage


def format_table(markets: dict) -> str:
    if not markets:
        return "  (waiting for data…)"
    rows = sorted(markets.values(), key=lambda m: m.impliedApy, reverse=True)
    lines = [
        f"{'Exchange':<10} {'Symbol':<35} {'Implied APY':>12} {'Underlying':>11} "
        f"{'TVL':>14} {'Days Left':>10}",
        "-" * 96,
    ]
    for m in rows:
        tvl_note = "" if m.exchange == "pendle" else " (asset)"
        lines.append(
            f"{m.exchange:<10} {m.symbol:<35} "
            f"{m.impliedApy * 100:>11.2f}% "
            f"{m.underlyingApy * 100:>10.2f}% "
            f"{m.tvl:>13,.0f}{tvl_note} "
            f"{m.daysToExpiry:>9.1f}d"
        )
    return "\n".join(lines)


async def main() -> None:
    token = os.getenv("MACKINAC_TOKEN")
    client = AsyncClient.from_token(token) if token else AsyncClient()

    markets: dict[str, RateMarketMessage] = {}
    last_print = 0.0

    async with client:
        async with client.subscribe("rates:all") as feed:
            print("Subscribing to all yield rate markets (Pendle + Spectra)…\n")
            async for msg in feed:
                if not isinstance(msg, RateMarketMessage):
                    continue

                key = f"{msg.exchange}:{msg.address}"
                markets[key] = msg

                now = asyncio.get_event_loop().time()
                if now - last_print > 2.0:
                    last_print = now
                    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    print(f"\033[2J\033[H[{ts} UTC]  {len(markets)} markets\n")
                    print(format_table(markets))


if __name__ == "__main__":
    asyncio.run(main())
