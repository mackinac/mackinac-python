"""historical_trades.py — pull Ostium XAU/USD trades and write to CSV.

By default fetches the last 23 hours (within the anonymous free-tier 24 h
window).  Set HOURS=168 (etc.) for a longer lookback — REST history beyond
24 h requires a JWT (Bearer auth); ``mk_*`` API keys are WS-only for now.

Run:
    python examples/historical_trades.py                       # anonymous, 23 h
    HOURS=168 MACKINAC_TOKEN=eyJ... python examples/historical_trades.py  # 7 d
"""
import asyncio
import csv
import os
import sys
from datetime import datetime, timedelta, timezone

from mackinac import AsyncClient


async def main() -> None:
    token = os.getenv("MACKINAC_TOKEN")
    hours = int(os.getenv("HOURS", "23"))
    if token:
        client = AsyncClient.from_token(token)
    else:
        client = AsyncClient()

    end   = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    out_path = "xau_usd_trades.csv"
    count = 0

    async with client:
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_ms", "time_utc", "price", "size", "side"])

            async for trade in client.history_trades(
                "ostium", "XAU/USD",
                start=int(start.timestamp() * 1000),
                end=int(end.timestamp() * 1000),
            ):
                dt = datetime.fromtimestamp(trade.time / 1000, tz=timezone.utc)
                side_label = {0: "sell", 1: "buy", 2: "unknown"}.get(trade.side, "?")
                writer.writerow([trade.time, dt.isoformat(), trade.price, trade.size, side_label])
                count += 1
                if count % 1000 == 0:
                    print(f"  {count:,} rows…", end="\r", flush=True)

    print(f"\nWrote {count:,} trades to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
