"""amm_fee_table.py — rebuild the AMM fee/depth table from live DepthMessage data.

On each ``depth`` message, constructs a pandas DataFrame mirroring the
AMM fee-tier impact table: one row per fee tier showing bid price, ask price,
and market impact at $1k / $10k / $100k / $1M notional.

Requires:
    pip install 'mackinac-client[tables]'

Run:
    python examples/amm_fee_table.py
"""
import asyncio
import os

import pandas as pd

from mackinac import AsyncClient, DepthMessage, QuoteMessage

SYMBOL = "WETH/USDC"
EXCHANGE = "uni"


def build_fee_table(quote: QuoteMessage | None, depth: DepthMessage) -> pd.DataFrame:
    """Build a DataFrame with one row per fee tier."""
    rows = []

    # Derive per-fee-tier bid/ask from the latest QuoteMessage (AMM levels carry fee)
    fee_prices: dict[int, dict] = {}
    if quote:
        for level in quote.bids:
            if level.fee is not None:
                fee_prices.setdefault(level.fee, {})["bid"] = level.price
        for level in quote.asks:
            if level.fee is not None:
                fee_prices.setdefault(level.fee, {})["ask"] = level.price

    # Impact estimates are per-symbol aggregates (not per-fee-tier in v1)
    impacts = {imp.usd: imp for imp in depth.impacts}

    for fee_ppm, prices in sorted(fee_prices.items()):
        bid = prices.get("bid")
        ask = prices.get("ask")
        mid = (bid + ask) / 2 if bid and ask else None
        row: dict = {
            "fee_bps": fee_ppm / 100,
            "bid":     round(bid, 4) if bid else None,
            "ask":     round(ask, 4) if ask else None,
            "spread_bps": round((ask - bid) / mid * 10_000, 2) if (bid and ask and mid) else None,
        }
        for usd_size in [1_000, 10_000, 100_000, 1_000_000]:
            imp = impacts.get(float(usd_size))
            label = f"${usd_size // 1000:,}k"
            if imp:
                row[f"buy_pct_{label}"]  = round(imp.buyPct, 4)
                row[f"sell_pct_{label}"] = round(imp.sellPct, 4)
            else:
                row[f"buy_pct_{label}"]  = None
                row[f"sell_pct_{label}"] = None
        rows.append(row)

    return pd.DataFrame(rows)


async def main() -> None:
    token = os.getenv("MACKINAC_TOKEN")
    client = AsyncClient.from_token(token) if token else AsyncClient()

    latest_quote: QuoteMessage | None = None

    async with client:
        print(f"Subscribing to {EXCHANGE}:{SYMBOL} depth…\n")
        async with client.subscribe(f"{EXCHANGE}:{SYMBOL}") as feed:
            async for msg in feed:
                if isinstance(msg, QuoteMessage) and msg.exchange == EXCHANGE:
                    latest_quote = msg

                if isinstance(msg, DepthMessage) and msg.exchange == EXCHANGE:
                    df = build_fee_table(latest_quote, msg)
                    if not df.empty:
                        print(f"\033[2J\033[H[{EXCHANGE}:{SYMBOL}  tick={msg.currentTick}]\n")
                        print(df.to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())
