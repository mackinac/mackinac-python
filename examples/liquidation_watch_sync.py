"""liquidation_watch_sync.py - watch on-chain lending liquidations live.

Subscribes to the consolidated ``lending:actions`` topic, filters for
``action == 'liquidate'``, and prints whale liquidations across Aave V3,
Compound V3, and Morpho Blue.

Async sibling: ``liquidation_watch_async.py`` -- same behaviour using AsyncClient.

Liquidations are sporadic.  Quiet markets can go many minutes without one;
volatile markets cascade.  No credentials required -- free tier covers
``lending:actions``.

Run:
    python examples/liquidation_watch_sync.py
"""
from datetime import datetime, timezone

from mackinac import Mackinac, LendingActionMessage


def fmt_action(a: LendingActionMessage) -> str:
    ts = datetime.fromtimestamp(a.time / 1000, tz=timezone.utc).strftime("%H:%M:%S")
    debt_usd  = f"${a.amountUsd:,.0f}" if a.amountUsd is not None else "$ ? "
    collateral = f"{a.collateralAsset}" if a.collateralAsset else "(unknown coll.)"
    return (
        f"[{ts}]  {a.exchange:<8}  {a.asset:<8}  "
        f"debt {debt_usd:<14}  collateral {collateral:<8}  "
        f"borrower {a.user[:10]}...  liquidator {a.liquidator[:10] if a.liquidator else '?'}..."
    )


def main() -> None:
    with Mackinac() as m:
        print("Watching lending:actions for liquidations (Ctrl+C to exit)...\n")
        liquidations = 0
        with m.subscribe("lending:actions") as feed:
            for msg in feed:
                if not isinstance(msg, LendingActionMessage):
                    continue
                if msg.action != "liquidate":
                    continue
                liquidations += 1
                print(fmt_action(msg))


if __name__ == "__main__":
    main()
