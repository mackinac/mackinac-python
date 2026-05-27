"""reconnect_pattern.py — demonstrate that the async iterator survives a
forced disconnect and continues delivering messages after auto-reconnect.

The library reconnects with exponential backoff (1s → 2s → … → 30s cap)
and re-subscribes all active symbols automatically.  The ``async for``
loop in user code sees no interruption.

Run:
    python examples/reconnect_pattern.py
"""
import asyncio

from mackinac import AsyncClient, PrintMessage, QuoteMessage


async def main() -> None:
    async with AsyncClient() as client:
        print("Subscribing to HL ETH feed…")
        msg_count = 0

        async with client.subscribe("hl:ETH") as feed:
            async for msg in feed:
                msg_count += 1

                if isinstance(msg, (QuoteMessage, PrintMessage)):
                    print(f"[{msg_count:4d}] {msg.type:<8} {msg.symbol}  "
                          f"(reconnect is transparent — keep counting)")

                # After 5 messages, forcibly close the underlying WS transport.
                # The engine will detect the close and reconnect automatically.
                if msg_count == 5:
                    print("\n>>> Forcing transport close to trigger reconnect…\n")
                    ws = feed._engine._ws
                    if ws is not None:
                        await ws.close()
                    # The next message will arrive after the auto-reconnect completes.

                if msg_count >= 15:
                    print(f"\nReceived {msg_count} messages across reconnect — done.")
                    break


if __name__ == "__main__":
    asyncio.run(main())
