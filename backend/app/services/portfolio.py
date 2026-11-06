"""Loads database records into the calculation engine and caches the replayed history."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import data_version
from app.engine.ledger import History, build_history, trade_observations
from app.engine.market import FxBook, PriceBook
from app.engine.types import AccountInfo, AssetInfo, Observation, Tx
from app.models import Account, Asset, FxRate, Portfolio, Price, Transaction, Valuation

_cache: dict[tuple, History] = {}


def ensure_portfolio(db: Session) -> Portfolio:
    p = db.scalar(select(Portfolio).limit(1))
    if p is None:
        p = Portfolio(name="My portfolio", base_currency=settings.base_currency)
        db.add(p)
        db.commit()
    return p


def to_tx(t: Transaction) -> Tx:
    return Tx(id=t.id, account_id=t.account_id, type=t.type, date=t.trade_date, asset_id=t.asset_id,
              quantity=t.quantity, price=t.price, amount=t.amount, currency=t.currency,
              counter_amount=t.counter_amount, counter_currency=t.counter_currency, fees=t.fees,
              fx_rate_to_base=t.fx_rate_to_base)


def load_history(db: Session, end: date | None = None) -> History:
    end = end or date.today()
    key = (data_version["value"], end)
    if key in _cache:
        return _cache[key]

    accounts = {a.id: AccountInfo(a.id, a.name, a.currency, a.tracks_cash, a.ownership_pct)
                for a in db.scalars(select(Account))}
    assets = {a.id: AssetInfo(a.id, a.name, a.asset_class, a.currency, a.symbol, a.liquidity, a.valuation_method)
              for a in db.scalars(select(Asset))}
    txs = [to_tx(t) for t in db.scalars(select(Transaction))]
    observations = trade_observations(txs)
    observations += [(p.asset_id, Observation(p.date, p.price, "market")) for p in db.scalars(select(Price))]
    observations += [(v.asset_id, Observation(v.date, v.price, "mark")) for v in db.scalars(select(Valuation))]
    fx = FxBook(settings.base_currency, [(r.currency, r.date, r.rate) for r in db.scalars(
        select(FxRate).where(FxRate.base == settings.base_currency))])

    history = build_history(txs, accounts, assets, PriceBook(observations), fx, end)
    _cache.clear()
    _cache[key] = history
    return history
