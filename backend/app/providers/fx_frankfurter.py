"""ECB reference rates via the free Frankfurter API (no key needed)."""

from datetime import date, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Account, Asset, FxRate, Transaction

SOURCE = "frankfurter"


def fetch(currency: str, base: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    url = f"{settings.fx_provider_url}/{start.isoformat()}..{end.isoformat()}"
    r = httpx.get(url, params={"base": currency, "symbols": base}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    rates = r.json().get("rates", {})
    return [(date.fromisoformat(d), Decimal(str(v[base]))) for d, v in rates.items() if base in v]


def currencies_in_use(db: Session) -> set[str]:
    found = set(db.scalars(select(Asset.currency))) | set(db.scalars(select(Account.currency)))
    found |= set(db.scalars(select(Transaction.currency)))
    found |= {c for c in db.scalars(select(Transaction.counter_currency)) if c}
    return {c for c in found if c and c != settings.base_currency}


def refresh(db: Session) -> dict:
    """Fetch missing daily rates for every currency in use, from the first transaction to today."""
    base = settings.base_currency
    first_tx = db.scalar(select(func.min(Transaction.trade_date)))
    if first_tx is None:
        return {"updated": {}, "errors": {}}
    today = date.today()
    updated, errors = {}, {}
    for ccy in sorted(currencies_in_use(db)):
        last = db.scalar(select(func.max(FxRate.date)).where(FxRate.currency == ccy, FxRate.base == base,
                                                             FxRate.source == SOURCE))
        start = (last + timedelta(days=1)) if last else first_tx - timedelta(days=7)
        if start > today:
            continue
        try:
            rows = fetch(ccy, base, start, today)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            errors[ccy] = str(e)
            continue
        have = set(db.scalars(select(FxRate.date).where(FxRate.currency == ccy, FxRate.base == base)))
        added = 0
        for d, rate in rows:
            if d not in have:
                db.add(FxRate(currency=ccy, base=base, date=d, rate=rate, source=SOURCE))
                added += 1
        updated[ccy] = added
    db.commit()
    return {"updated": updated, "errors": errors}
