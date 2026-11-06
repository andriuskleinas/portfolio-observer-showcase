from datetime import date
from decimal import Decimal
from typing import Sequence

from app.engine.types import ONE, ZERO


def twr(values: Sequence[Decimal], net_flows: Sequence[Decimal], start_value: Decimal) -> Decimal | None:
    """Daily chain-linked time-weighted return.

    values[i] is the end-of-day value and net_flows[i] the day's net external flow.
    Net inflows are treated as arriving at the start of the day and net outflows as
    leaving at the end, so a full sale doesn't read as a -100% day.
    """
    growth, prev, used = ONE, start_value, False
    for v, f in zip(values, net_flows):
        inflow = f if f > 0 else ZERO
        outflow = -f if f < 0 else ZERO
        denom = prev + inflow
        if denom > 0:
            growth *= (v + outflow) / denom
            used = True
        prev = v
    return growth - ONE if used else None


def annualize(period_return: Decimal | None, days: int) -> Decimal | None:
    """Annualize only periods of a year or more (PERF-05)."""
    if period_return is None or days < 365 or period_return <= -1:
        return None
    return Decimal(str((1 + float(period_return)) ** (365.0 / days) - 1))


def xirr(cashflows: Sequence[tuple[date, Decimal]]) -> Decimal | None:
    """Annualized internal rate of return for irregular cash flows (investor's view:
    money paid in is negative, money received and the ending value are positive)."""
    flows = [(d, float(a)) for d, a in cashflows if a != 0]
    if not flows or not any(a > 0 for _, a in flows) or not any(a < 0 for _, a in flows):
        return None
    d0 = min(d for d, _ in flows)
    ts = [((d - d0).days / 365.0, a) for d, a in flows]

    def npv(r: float) -> float:
        return sum(a / (1 + r) ** t for t, a in ts)

    lo, hi = -0.999999, 1.0
    f_lo = npv(lo)
    f_hi = npv(hi)
    while f_lo * f_hi > 0 and hi < 1e6:
        hi *= 4
        f_hi = npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-9 or (hi - lo) < 1e-12:
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return Decimal(str(round((lo + hi) / 2, 10)))


def period_from_annual(annual: Decimal | None, days: int) -> Decimal | None:
    if annual is None:
        return None
    return Decimal(str((1 + float(annual)) ** (days / 365.0) - 1))
