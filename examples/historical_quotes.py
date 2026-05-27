"""historical_quotes.py — fetch the last hour of ETH quote snapshots and compute OHLC.

Quote snapshots are recorded every ~5 seconds.  This example pulls the last
hour and computes open/high/low/close mid-prices to show how historical quote
data can be used for price reconstruction.

Requires a JWT or API key (historical data beyond 1 day is tier-gated).
Anonymous users can pass start/end within the last 24 hours.

Run:
    MACKINAC_TOKEN=eyJ... python examples/historical_quotes.py

    # Anonymous (last 30 minutes — within free-tier 1-day window):
    python examples/historical_quotes.py
"""
import os
from datetime import datetime, timedelta, timezone

from mackinac import Mackinac


def main() -> None:
    token = os.getenv("MACKINAC_TOKEN")
    m = Mackinac.from_token(token) if token else Mackinac()

    end   = datetime.now(timezone.utc)
    start = end - timedelta(minutes=30)  # free-tier safe default

    mids: list[float] = []

    with m:
        print(f"Fetching ETH quote snapshots {start:%H:%M} → {end:%H:%M} UTC…")
        for snap in m.history_quotes(
            "hl", "ETH",
            start=int(start.timestamp() * 1000),
            end=int(end.timestamp() * 1000),
        ):
            if snap.bids and snap.asks:
                mids.append((snap.bids[0].price + snap.asks[0].price) / 2)

    if not mids:
        print("No data returned.")
        return

    print(f"\n  snapshots : {len(mids):,}")
    print(f"  open      : {mids[0]:,.4f}")
    print(f"  high      : {max(mids):,.4f}")
    print(f"  low       : {min(mids):,.4f}")
    print(f"  close     : {mids[-1]:,.4f}")
    print(f"  range     : {max(mids) - min(mids):,.4f}")


if __name__ == "__main__":
    main()
