"""quotes_and_trades.py — stream live quotes and trades together for HL ETH.

Shows the two most common message types side by side.  Uses types= to
filter out everything else (funding, depth, etc.) so the loop only sees
what it needs.

Requires no credentials (free tier, 3-symbol cap).

Run:
    python examples/quotes_and_trades.py
"""
from mackinac import Mackinac, PrintMessage, QuoteMessage


def main() -> None:
    with Mackinac() as m:
        n = len(m.live_symbols("hl"))
        print(f"Connected — {n} HL symbols available.  Streaming ETH quotes + trades…\n")

        with m.subscribe("hl:ETH", types=(QuoteMessage, PrintMessage)) as feed:
            for msg in feed:
                if isinstance(msg, QuoteMessage):
                    bid = msg.bids[0].price if msg.bids else "—"
                    ask = msg.asks[0].price if msg.asks else "—"
                    print(f"  quote   bid {bid:>12}  ask {ask:>12}")
                else:  # PrintMessage
                    side = "↑ buy " if msg.side == 1 else "↓ sell"
                    print(f"  trade  {side}  {msg.price:>12,.2f}  ×  {msg.size}")


if __name__ == "__main__":
    main()
