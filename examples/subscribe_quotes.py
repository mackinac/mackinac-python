"""subscribe_quotes.py — stream live top-of-book quotes for HL ETH.

Requires no credentials (free tier, 2-symbol cap).

Run:
    python examples/subscribe_quotes.py
"""
import asyncio

from mackinac import AsyncClient, QuoteMessage


async def main() -> None:
    async with AsyncClient() as client:
        print("Connecting to HL ETH quote stream…")
        async with client.subscribe("hl:ETH") as feed:
            async for msg in feed:
                if not isinstance(msg, QuoteMessage):
                    continue

                best_bid = msg.bids[0] if msg.bids else None
                best_ask = msg.asks[0] if msg.asks else None

                if best_bid and best_ask:
                    spread = best_ask.price - best_bid.price
                    mid    = (best_bid.price + best_ask.price) / 2
                    print(
                        f"[{msg.exchange}:{msg.symbol}]  "
                        f"bid {best_bid.price:.2f} x {best_bid.size:.4f}  "
                        f"ask {best_ask.price:.2f} x {best_ask.size:.4f}  "
                        f"spread {spread:.2f}  mid {mid:.2f}"
                    )


if __name__ == "__main__":
    asyncio.run(main())
