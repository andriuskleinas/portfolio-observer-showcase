"""Dashboard and holding-detail analytics (PERF-*, VIEW-01..06)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.records import _att, _tx_out
from app.api.schemas import AssetOut, ValuationOut
from app.db import get_db
from app.engine.analytics import (PERIODS, Filters, aggregate, allocation, holding_rows, inception, metrics,
                                  period_start, select_keys, series)
from app.engine.types import ZERO
from app.models import Asset, Attachment, Transaction, Valuation
from app.services.portfolio import load_history
from app.taxonomy import ASSET_CLASSES

router = APIRouter(prefix="/api")


def _check_period(period: str) -> str:
    p = period.upper()
    if p not in PERIODS:
        raise HTTPException(422, f"Period must be one of {', '.join(PERIODS)}")
    return p


@router.get("/dashboard")
def dashboard(period: str = "YTD", asset_class: list[str] = Query(default=[]),
              account_id: list[int] = Query(default=[]), currency: list[str] = Query(default=[]),
              include_illiquid: bool = True, db: Session = Depends(get_db)):
    period = _check_period(period)
    h = load_history(db)
    f = Filters(asset_classes=set(asset_class) or None, account_ids=set(account_id) or None,
                currencies={c.upper() for c in currency} or None, include_illiquid=include_illiquid)
    keys = select_keys(h, f)
    agg = aggregate(h, keys)
    end = h.end or date.today()
    start = period_start(period, end, inception(agg) or end)
    m = metrics(h, keys, agg, start, end)
    rows = holding_rows(h, keys, start, end)
    holdings = [r for r in rows if r["kind"] == "holding"]
    cost = sum((r["cost_basis"] for r in holdings if r["cost_basis"] is not None), ZERO)
    unrealized = sum((r["unrealized"] for r in holdings if r["unrealized"] is not None), ZERO)
    movers = sorted((r for r in holdings if r["period_gain"]), key=lambda r: abs(r["period_gain"]), reverse=True)[:5]

    present_classes = sorted({r["asset_class"] for r in rows}, key=lambda c: list(ASSET_CLASSES).index(c))
    return {
        "base_currency": h.base,
        "as_of": end.isoformat(),
        "period": period,
        "summary": {**m, "cost_basis": cost, "unrealized": unrealized},
        "series": series(agg, start, end),
        "allocation": allocation(h, keys, end),
        "holdings": rows,
        "movers": movers,
        "stale": [r for r in holdings if r["stale"]],
        "warnings": h.warnings,
        "filter_options": {
            "accounts": [{"id": a.id, "name": a.name} for a in sorted(h.accounts.values(), key=lambda a: a.name)],
            "asset_classes": [{"key": c, "label": ASSET_CLASSES[c]["label"]} for c in present_classes],
        },
    }


@router.get("/assets/{asset_id}/detail")
def asset_detail(asset_id: int, period: str = "ALL", db: Session = Depends(get_db)):
    period = _check_period(period)
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found")
    h = load_history(db)
    keys = select_keys(h, Filters(asset_ids={asset_id}))
    agg = aggregate(h, keys)
    end = h.end or date.today()
    inc = inception(agg) or end
    start = period_start(period, end, inc)

    lots = []
    for key in keys:
        hs = h.holdings.get(key)
        if hs is None:
            continue
        own = h.accounts[key[1]].ownership
        for lot in hs.lots:
            lots.append({"account": h.accounts[key[1]].name, "date": lot.date.isoformat(), "quantity": lot.quantity,
                         "cost_local": lot.cost_local * own, "cost_base": lot.cost_base * own,
                         "unit_cost": lot.cost_local / lot.quantity if lot.quantity else None})

    txs = db.scalars(select(Transaction).where(Transaction.asset_id == asset_id)
                     .order_by(Transaction.trade_date.desc(), Transaction.id.desc())).unique().all()
    prices = h.prices.series(asset_id)
    return {
        "base_currency": h.base,
        "as_of": end.isoformat(),
        "period": period,
        "asset": AssetOut.model_validate(asset).model_dump(mode="json"),
        "class_label": ASSET_CLASSES.get(asset.asset_class, {}).get("label"),
        "summary": metrics(h, keys, agg, start, end),
        "all_time": metrics(h, keys, agg, inc, end),
        "positions": holding_rows(h, keys, start, end, include_closed=True),
        "series": series(agg, start, end),
        "prices": [{"date": o.date.isoformat(), "price": o.price, "source": o.source}
                   for o in prices if start <= o.date <= end][-1500:],
        "lots": lots,
        "transactions": [_tx_out(t).model_dump(mode="json") for t in txs],
        "valuations": [ValuationOut.model_validate(v).model_dump(mode="json") for v in db.scalars(
            select(Valuation).where(Valuation.asset_id == asset_id).order_by(Valuation.date.desc()))],
        "attachments": [_att(a) for a in db.scalars(
            select(Attachment).where(Attachment.asset_id == asset_id).order_by(Attachment.uploaded_at.desc()))],
        "warnings": [w for w in h.warnings if asset.name in w],
    }
