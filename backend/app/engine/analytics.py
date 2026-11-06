"""Selections, periods and metrics on top of a replayed History."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.engine.ledger import History
from app.engine.returns import annualize, period_from_annual, twr, xirr
from app.engine.types import ZERO
from app.taxonomy import ASSET_CLASSES

PERIODS = ["1D", "1W", "MTD", "1M", "3M", "YTD", "1Y", "3Y", "5Y", "ALL"]


@dataclass
class Filters:
    asset_classes: set[str] | None = None
    account_ids: set[int] | None = None
    currencies: set[str] | None = None
    asset_ids: set[int] | None = None
    include_illiquid: bool = True


def key_meta(h: History, key: tuple) -> dict:
    if key[0] == "c":
        return {"kind": "cash", "account_id": key[1], "asset_id": None, "asset_class": "cash",
                "currency": key[2], "liquidity": "liquid"}
    a = h.assets[key[2]]
    return {"kind": "holding", "account_id": key[1], "asset_id": a.id, "asset_class": a.asset_class,
            "currency": a.currency, "liquidity": a.liquidity}


def select_keys(h: History, f: Filters) -> list[tuple]:
    keys = []
    for key in h.values:
        m = key_meta(h, key)
        if f.asset_classes is not None and m["asset_class"] not in f.asset_classes:
            continue
        if f.account_ids is not None and m["account_id"] not in f.account_ids:
            continue
        if f.currencies is not None and m["currency"] not in f.currencies:
            continue
        if f.asset_ids is not None and m["asset_id"] not in f.asset_ids:
            continue
        if not f.include_illiquid and m["liquidity"] == "illiquid":
            continue
        keys.append(key)
    return keys


def _minus_months(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    last_day = (date(y + (m // 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day))


def period_start(period: str, end: date, inception: date) -> date:
    p = period.upper()
    starts = {
        "1D": end,
        "1W": end - timedelta(days=6),
        "MTD": end.replace(day=1),
        "1M": _minus_months(end, 1) + timedelta(days=1),
        "3M": _minus_months(end, 3) + timedelta(days=1),
        "YTD": date(end.year, 1, 1),
        "1Y": _minus_months(end, 12) + timedelta(days=1),
        "3Y": _minus_months(end, 36) + timedelta(days=1),
        "5Y": _minus_months(end, 60) + timedelta(days=1),
    }
    start = starts.get(p, inception)
    return max(start, inception)


@dataclass
class Aggregate:
    dates: list[date]
    values: list[Decimal]
    flows: list[Decimal]


def aggregate(h: History, keys: list[tuple]) -> Aggregate:
    n = len(h.dates)
    values = [ZERO] * n
    flows = [ZERO] * n
    for key in keys:
        for i, v in enumerate(h.values[key]):
            if v:
                values[i] += v
        for d, f in h.flows.get(key, {}).items():
            i = h.index(d)
            if i >= 0:
                flows[i] += f
    return Aggregate(h.dates, values, flows)


def inception(agg: Aggregate) -> date | None:
    for d, v, f in zip(agg.dates, agg.values, agg.flows):
        if v or f:
            return d
    return None


def metrics(h: History, keys: list[tuple], agg: Aggregate, start: date, end: date) -> dict:
    i0, i1 = h.index(start), h.index(end)
    if i0 < 0 or i1 < 0:
        return _empty_metrics(start, end)
    days = (end - start).days + 1
    start_value = agg.values[i0 - 1] if i0 > 0 else ZERO
    end_value = agg.values[i1]
    window_values = agg.values[i0:i1 + 1]
    window_flows = agg.flows[i0:i1 + 1]
    net_flows = sum(window_flows, ZERO)
    inflows = sum((f for f in window_flows if f > 0), ZERO)
    outflows = -sum((f for f in window_flows if f < 0), ZERO)

    t = twr(window_values, window_flows, start_value)

    cfs = []
    if start_value:
        cfs.append((start - timedelta(days=1), -start_value))
    cfs += [(d, -f) for d, f in zip(agg.dates[i0:i1 + 1], window_flows) if f]
    cfs.append((end, end_value))
    mwr_annual = xirr(cfs)

    invested = start_value + inflows
    sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for key in keys:
        for e in h.events_by_key.get(key, ()):
            if start <= e.date <= end:
                sums[e.kind] += e.amount

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "start_value": start_value,
        "end_value": end_value,
        "net_flows": net_flows,
        "inflows": inflows,
        "outflows": outflows,
        "gain": end_value - start_value - net_flows,
        "twr": t,
        "twr_annualized": annualize(t, days),
        "mwr": period_from_annual(mwr_annual, days) if mwr_annual is not None else None,
        "mwr_annualized": mwr_annual if days >= 365 else None,
        "moic": (end_value + outflows) / invested if invested > 0 else None,
        "income": sums["income"],
        "realized": sums["realized"],
        "fees": sums["fee"],
        "taxes": sums["tax"],
    }


def _empty_metrics(start: date, end: date) -> dict:
    return {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1,
            "start_value": ZERO, "end_value": ZERO, "net_flows": ZERO, "inflows": ZERO, "outflows": ZERO,
            "gain": ZERO, "twr": None, "twr_annualized": None, "mwr": None, "mwr_annualized": None,
            "moic": None, "income": ZERO, "realized": ZERO, "fees": ZERO, "taxes": ZERO}


def series(agg: Aggregate, start: date, end: date, max_points: int = 400) -> list[dict]:
    """Value and cumulative net invested capital over time, thinned for charting."""
    out, invested = [], ZERO
    rows = []
    for d, v, f in zip(agg.dates, agg.values, agg.flows):
        invested += f
        if start <= d <= end:
            rows.append((d, v, invested))
    if not rows:
        return out
    step = max(1, len(rows) // max_points)
    picked = rows[::step]
    if picked[-1] is not rows[-1]:
        picked.append(rows[-1])
    return [{"date": d.isoformat(), "value": v, "invested": inv} for d, v, inv in picked]


def holding_rows(h: History, keys: list[tuple], start: date, end: date, include_closed: bool = False) -> list[dict]:
    i1 = h.index(end)
    total = sum((h.values[k][i1] for k in keys), ZERO) if i1 >= 0 else ZERO
    rows = []
    for key in keys:
        value = h.values[key][i1] if i1 >= 0 else ZERO
        single = aggregate(h, [key])
        m = metrics(h, [key], single, start, end)
        acct = h.accounts[key[1]]
        all_time: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for e in h.events_by_key.get(key, ()):
            all_time[e.kind] += e.amount
        base = {"key": "-".join(map(str, key)), "account_id": acct.id, "account": acct.name, "value": value,
                "weight": value / total if total else None, "period_gain": m["gain"], "period_return": m["twr"],
                "income": all_time["income"], "realized": all_time["realized"]}
        if key[0] == "c":
            if not value and not include_closed:
                continue
            rows.append({**base, "kind": "cash", "asset_id": None, "name": f"Cash {key[2]}", "symbol": key[2],
                         "asset_class": "cash", "currency": key[2], "quantity": h.cash.get(key, ZERO),
                         "price": None, "price_date": None, "price_source": None, "stale": False,
                         "cost_basis": None, "unrealized": None, "unrealized_pct": None})
            continue
        hs = h.holdings[key]
        if hs.quantity == 0 and not value and not include_closed:
            continue
        asset = h.assets[key[2]]
        own = acct.ownership
        obs = h.prices.latest(asset.id, end)
        cost = hs.cost_base * own
        unrealized = value - cost if hs.quantity else None
        stale_days = ASSET_CLASSES.get(asset.asset_class, {}).get("stale_days")
        stale = bool(obs and stale_days is not None and hs.quantity and (end - obs.date).days > stale_days)
        rows.append({**base, "kind": "holding", "asset_id": asset.id, "name": asset.name, "symbol": asset.symbol,
                     "asset_class": asset.asset_class, "currency": asset.currency, "quantity": hs.quantity,
                     "price": obs.price if obs else None, "price_date": obs.date.isoformat() if obs else None,
                     "price_source": obs.source if obs else None, "stale": stale, "cost_basis": cost,
                     "unrealized": unrealized,
                     "unrealized_pct": (unrealized / cost) if (unrealized is not None and cost > 0) else None})
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows


def allocation(h: History, keys: list[tuple], end: date) -> list[dict]:
    i1 = h.index(end)
    by_class: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for key in keys:
        v = h.values[key][i1] if i1 >= 0 else ZERO
        if v:
            by_class[key_meta(h, key)["asset_class"]] += v
    total = sum(by_class.values(), ZERO)
    out = [{"asset_class": c, "label": ASSET_CLASSES.get(c, {}).get("label", c), "value": v,
            "weight": v / total if total else None} for c, v in by_class.items()]
    out.sort(key=lambda r: r["value"], reverse=True)
    return out
