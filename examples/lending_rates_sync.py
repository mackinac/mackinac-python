"""lending_rates_sync.py - live lending-rate snapshot table across Aave, Compound, Morpho.

Subscribes to ``aave:all``, ``compound:all``, and ``morpho:all`` and maintains
a pandas DataFrame of supply/borrow APY, utilization, and TVL per
(exchange, asset).  Re-prints the top-10-by-TVL view every ~5 seconds.

Async sibling: ``lending_rates_async.py`` -- same behaviour using AsyncClient.

Requires ``pandas``::

    pip install 'mackinac-client[tables]'

Anonymous tier: 3 topics is at the free-tier IP cap.  Pass MACKINAC_TOKEN
to subscribe alongside other anonymous sessions.

Note: the backend's per-event rate_market emission and 30s Multicall3 backstop
were sparse as of 0.2.0 release — you may see the subscribe banner without an
immediate table.  Action events flow normally; if you want to see lending
activity right away, run ``liquidation_watch_sync.py`` alongside this script.

Run:
    python examples/lending_rates_sync.py
    MACKINAC_TOKEN=mk_live_... python examples/lending_rates_sync.py
"""
import os
import time

import pandas as pd

from mackinac import Mackinac, RateMarketMessage


def to_row(msg: RateMarketMessage) -> dict:
    return {
        "exchange":         msg.exchange,
        "asset":            msg.asset or msg.symbol,
        "supply_apy%":      msg.underlyingApy * 100,
        "borrow_apy%":      (msg.borrowApy or 0) * 100,
        "utilization%":     (msg.utilization or 0) * 100,
        "available_usd":    msg.available or 0,
        "tvl_usd":          msg.tvl,
    }


def render(markets: dict) -> str:
    df = pd.DataFrame(list(markets.values()))
    if df.empty:
        return "(no rate_market frames yet)"
    df = df.sort_values("tvl_usd", ascending=False).head(10)
    df["supply_apy%"]   = df["supply_apy%"].map("{:>6.2f}%".format)
    df["borrow_apy%"]   = df["borrow_apy%"].map("{:>6.2f}%".format)
    df["utilization%"]  = df["utilization%"].map("{:>5.1f}%".format)
    df["available_usd"] = df["available_usd"].map("{:>13,.0f}".format)
    df["tvl_usd"]       = df["tvl_usd"].map("{:>14,.0f}".format)
    return df.to_string(index=False)


def main() -> None:
    token  = os.getenv("MACKINAC_TOKEN")
    client = Mackinac.from_token(token) if token else Mackinac()
    markets: dict[tuple[str, str], dict] = {}
    last_print = 0.0

    with client as m:
        print("Subscribing to aave:all + compound:all + morpho:all ...\n")
        with m.subscribe("aave:all", "compound:all", "morpho:all") as feed:
            for msg in feed:
                if not isinstance(msg, RateMarketMessage):
                    continue
                key = (msg.exchange, msg.asset or msg.symbol)
                markets[key] = to_row(msg)
                now = time.monotonic()
                if now - last_print > 5.0:
                    last_print = now
                    print(f"\n[{len(markets)} markets tracked]")
                    print(render(markets))


if __name__ == "__main__":
    main()
