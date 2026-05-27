"""live_trades.py — stream live ETH trade executions from Hyperliquid.

Uses the ``types=`` filter so every message in the loop is a PrintMessage —
no isinstance check or branching needed.

Requires no credentials (free tier, 3-symbol cap).

Run:
    python examples/live_trades.py
"""
from mackinac import Mackinac, PrintMessage

SIDE = {0: "sell", 1: "buy ", 2: "?   "}


def main() -> None:
    with Mackinac() as m:
        print(f"HL has {len(m.live_symbols('hl'))} symbols live.  Streaming ETH trades…\n")

        with m.subscribe("hl:ETH", types=PrintMessage) as feed:
            for trade in feed:
                side = SIDE.get(trade.side, "?")
                print(
                    f"{side}  {trade.price:>12,.2f}  ×  {trade.size:<10}"
                    + (f"  block {trade.blockNumber}" if trade.blockNumber else "")
                )


if __name__ == "__main__":
    main()
