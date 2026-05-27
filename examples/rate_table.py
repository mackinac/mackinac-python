"""rate_table.py — build a live pandas DataFrame from rate_market messages.

Subscribes to rates:all and upserts rows keyed by (exchange, symbol) on each
update.  Displays the table sorted by implied APY every ~3 seconds — analogous
to the rate widget snapshot view in the Mackinac UI.

Columns:
  exchange, symbol, implied_apy%, underlying_apy%, lp_apy%,
  tvl (USD for Pendle; asset-units for Spectra v1),
  volume_24h (USD; always 0 for Spectra v1), days_to_expiry

Requires:
    pip install 'mackinac-client[tables]'

Run:
    python examples/rate_table.py
"""
import asyncio
import os
from datetime import datetime, timezone

import pandas as pd

from mackinac import AsyncClient, RateMarketMessage


def build_df(markets: dict[str, RateMarketMessage]) -> pd.DataFrame:
    rows = []
    for msg in markets.values():
        tvl_label = msg.tvl if msg.exchange == "pendle" else f"{msg.tvl:,.0f} (asset)"
        rows.append({
            "exchange":       msg.exchange,
            "symbol":         msg.symbol,
            "implied_apy%":   round(msg.impliedApy * 100, 3),
            "underlying_apy%":round(msg.underlyingApy * 100, 3),
            "lp_apy%":        round(msg.lpApy * 100, 3),
            "tvl":            tvl_label,
            "vol_24h_usd":    msg.volume24h,
            "days_to_expiry": round(msg.daysToExpiry, 1),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values("implied_apy%", ascending=False).reset_index(drop=True)


async def main() -> None:
    token = os.getenv("MACKINAC_TOKEN")
    client = AsyncClient.from_token(token) if token else AsyncClient()

    markets: dict[str, RateMarketMessage] = {}
    last_display = 0.0

    async with client:
        print("Subscribing to all yield rate markets…\n")
        async with client.subscribe("rates:all") as feed:
            async for msg in feed:
                if not isinstance(msg, RateMarketMessage):
                    continue

                key = f"{msg.exchange}:{msg.address}"
                markets[key] = msg

                now = asyncio.get_event_loop().time()
                if now - last_display < 3.0:
                    continue

                last_display = now
                df = build_df(markets)
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"\033[2J\033[H[{ts} UTC]  {len(df)} markets\n")
                if not df.empty:
                    print(df.to_string(index=False, max_colwidth=40))


if __name__ == "__main__":
    asyncio.run(main())
