"""multi_venue_basis.py — compute live cross-venue basis between HL ETH perp,
Uniswap V3 WETH/USDC spot, and Lighter ETH perp.

Shows the normalized data model: the same QuoteMessage fields work across
CLOB, AMM, and oracle venues.

Anonymous: 3 symbols is at the free-tier cap, so make sure no other anonymous
sessions are active from your IP.  Pass MACKINAC_TOKEN to bypass the cap.

Run:
    python examples/multi_venue_basis.py
    MACKINAC_TOKEN=mk_live_... python examples/multi_venue_basis.py
"""
import asyncio
import os
from datetime import datetime, timezone

from mackinac import AsyncClient, QuoteMessage

SUBSCRIPTIONS = ["hl:ETH", "uni:WETH/USDC", "lighter:ETH"]

# Key used to store latest mid-price per venue
LABEL = {
    "hl:ETH":         "HL perp",
    "uni:WETH/USDC":  "Uni V3 spot",
    "lighter:ETH":    "Lighter perp",
}


def mid(msg: QuoteMessage) -> float | None:
    if msg.bids and msg.asks:
        return (msg.bids[0].price + msg.asks[0].price) / 2
    if msg.bids:
        return msg.bids[0].price
    if msg.asks:
        return msg.asks[0].price
    return None


async def main() -> None:
    latest: dict[str, float] = {}
    token = os.getenv("MACKINAC_TOKEN")
    client = AsyncClient.from_token(token) if token else AsyncClient()

    async with client:
        print("Subscribing to HL / Uni / Lighter ETH quotes…\n")
        async with client.subscribe(*SUBSCRIPTIONS) as feed:
            async for msg in feed:
                if not isinstance(msg, QuoteMessage):
                    continue

                key = f"{msg.exchange}:{msg.symbol}"
                price = mid(msg)
                if price is None:
                    continue
                latest[key] = price

                if len(latest) < 3:
                    continue  # wait until we have all three

                hl    = latest.get("hl:ETH")
                uni   = latest.get("uni:WETH/USDC")
                light = latest.get("lighter:ETH")

                if not (hl and uni and light):
                    continue

                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                hl_uni_bps   = (hl   - uni)   / uni   * 10_000
                hl_light_bps = (hl   - light) / light * 10_000
                print(
                    f"[{ts}]  "
                    f"HL {hl:>10.2f}  "
                    f"Uni {uni:>10.2f}  "
                    f"Lighter {light:>10.2f}  │  "
                    f"HL–Uni {hl_uni_bps:>+7.1f}bps  "
                    f"HL–Lighter {hl_light_bps:>+7.1f}bps"
                )


if __name__ == "__main__":
    asyncio.run(main())
