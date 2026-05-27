"""
Funding rates as carry cost
===========================
Companion code for https://mackinac.io/blog/funding-rates-vs-futures-carry/

The blog contrasts three carry regimes:

  CME futures    — carry is deterministic, locked into the basis at entry
                   formula: r × (DTE / 365)
  HL perpetual   — carry is explicit and variable, unknown at entry;
                   longs pay shorts when perp trades above spot
  Ostium XAU/USD — carry is explicit but anchored to real-world rates
                   (SOFR + gold lease rate); historically 13–30% annualised

Usage:
    python examples/funding_carry.py                     # free tier (12 h)
    python examples/funding_carry.py mk_live_...         # API key (30 d)
"""

import sys
from datetime import datetime, timedelta, timezone

from mackinac import Mackinac

# ── Parameters ─────────────────────────────────────────────────────────────────

API_KEY  = sys.argv[1] if len(sys.argv) > 1 else None
HOURS    = 30 * 24 if API_KEY else 12   # free tier: stay within 24 h window
NOTIONAL = 100_000                       # USD position size
RISK_FREE = 0.053                        # SOFR proxy — the CME carry benchmark

end   = datetime.now(timezone.utc)
start = end - timedelta(hours=HOURS)

# ── Helpers ────────────────────────────────────────────────────────────────────

def carry_cost(rates, hours, notional):
    """
    Funding data is recorded at sub-minute frequency.  ratePct is an
    annualised %; intervalHrs is the venue's settlement cadence (constant
    per venue, not the duration of each record).

    Correct approach: time-weighted average annualised rate × elapsed time.
    """
    if not rates:
        return 0.0, 0.0
    avg_ann_pct = sum(r.ratePct for r in rates) / len(rates)   # annualised %
    cost = notional * (avg_ann_pct / 100) * (hours / 8_760)    # 8760 h/year
    return avg_ann_pct, cost

# ── Fetch data & compute ───────────────────────────────────────────────────────

client = Mackinac.from_api_key(API_KEY) if API_KEY else Mackinac()

with client as m:

    # ── CME: deterministic carry, locked at entry ───────────────────────────────
    # The futures basis embeds r × (DTE/365) of financing cost at the moment you
    # buy.  There are no subsequent surprises — but you must roll on expiry.
    cme_ann  = RISK_FREE * 100                              # annualised %
    cme_cost = NOTIONAL * RISK_FREE * (HOURS / 8_760)      # dollar cost over window

    # ── HL: variable perpetual funding, explicit, market-demand driven ──────────
    # Positive rate = longs pay shorts (perp premium over spot).
    # The rate floats continuously — unknown at entry, can spike during squeezes.
    hl_rates = list(m.history_funding("hl", "ETH", start=start, end=end))
    hl_ann, hl_cost = carry_cost(hl_rates, HOURS, NOTIONAL)

    # ── Ostium XAU/USD: real-world carry, anchored to futures curves ────────────
    # For RWAs, Ostium charges an explicit rollover fee calibrated to the
    # real-world cost of carry — SOFR + lease rate + storage for gold.
    # This is more predictable than HL funding, but structurally higher:
    # the blog notes gold has run 13–30% annualised, far above pure SOFR.
    xau_rates = list(m.history_funding("ostium", "XAU/USD", start=start, end=end))
    xau_ann, xau_cost = carry_cost(xau_rates, HOURS, NOTIONAL)

# ── Output ─────────────────────────────────────────────────────────────────────

days_label = f"{HOURS // 24}d" if HOURS >= 24 else f"{HOURS}h"
print(f"\nCarry cost -- ${NOTIONAL:,} long position, {days_label} window\n")
print(f"  {'Venue':<22}  {'Ann. rate':>10}  {'Cost on $100k':>14}  Known at entry?")
print(f"  {'-'*22}  {'-'*10}  {'-'*14}  {'-'*18}")

# CME: annualised rate is just SOFR -- constant, that's what makes it deterministic
print(f"  {'CME ETH (est.)':<22}  {cme_ann:>9.2f}%  ${cme_cost:>12,.2f}  Yes -- locked in")

# HL: same trade, same notional, but the rate varied every few seconds
print(f"  {'HL ETH (perp)':<22}  {hl_ann:>9.2f}%  ${hl_cost:>12,.2f}  No -- floats with demand")

# Ostium XAU: rate is anchored to commodity carry, not OI -- more stable but higher
print(f"  {'Ostium XAU/USD':<22}  {xau_ann:>9.2f}%  ${xau_cost:>12,.2f}  Partially -- rate-anchored")

print(f"\n  {len(hl_rates):,} HL samples  {len(xau_rates):,} XAU/USD samples over {days_label}")
if not API_KEY:
    print("  -> pass an API key as the first argument for 30 days of history\n")
else:
    print()
