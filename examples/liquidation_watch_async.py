"""liquidation_watch_async.py - watch on-chain lending liquidations live.

Async sibling of ``liquidation_watch_sync.py``.  Identical output, identical
structure -- only ``Mackinac`` -> ``AsyncClient`` and the three async keywords
change.

Run:
    python examples/liquidation_watch_async.py
"""
import asyncio
from datetime import datetime, timezone

from mackinac import AsyncClient, LendingActionMessage


def fmt_action(a: LendingActionMessage) -> str:
    ts = datetime.fromtimestamp(a.time / 1000, tz=timezone.utc).strftime("%H:%M:%S")
    debt_usd  = f"${a.amountUsd:,.0f}" if a.amountUsd is not None else "$ ? "
    collateral = f"{a.collateralAsset}" if a.collateralAsset else "(unknown coll.)"
    return (
        f"[{ts}]  {a.exchange:<8}  {a.asset:<8}  "
        f"debt {debt_usd:<14}  collateral {collateral:<8}  "
        f"borrower {a.user[:10]}...  liquidator {a.liquidator[:10] if a.liquidator else '?'}..."
    )


async def main() -> None:
    async with AsyncClient() as client:
        print("Watching lending:actions for liquidations (Ctrl+C to exit)...\n")
        liquidations = 0
        async with client.subscribe("lending:actions") as feed:
            async for msg in feed:
                if not isinstance(msg, LendingActionMessage):
                    continue
                if msg.action != "liquidate":
                    continue
                liquidations += 1
                print(fmt_action(msg))


if __name__ == "__main__":
    asyncio.run(main())
