"""Metadata, system status (NFR-05) and FX refresh."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.engine.analytics import PERIODS
from app.models import Account, Asset, FxRate, ImportBatch, Price, Transaction, Valuation
from app.providers import fx_frankfurter
from app.services.portfolio import load_history
from app.taxonomy import ACCOUNT_TYPES, ASSET_CLASSES, TX_TYPES, VALUATION_METHODS

router = APIRouter(prefix="/api")


@router.get("/meta")
def meta():
    return {"base_currency": settings.base_currency, "periods": PERIODS,
            "asset_classes": [{"key": k, **v} for k, v in ASSET_CLASSES.items()],
            "tx_types": [{"key": k, **v} for k, v in TX_TYPES.items()],
            "account_types": [{"key": k, **v} for k, v in ACCOUNT_TYPES.items()],
            "valuation_methods": VALUATION_METHODS}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    fx = db.execute(select(FxRate.currency, func.max(FxRate.date), func.count()).where(
        FxRate.base == settings.base_currency).group_by(FxRate.currency)).all()
    last_import = db.scalar(select(ImportBatch).where(ImportBatch.status == "committed")
                            .order_by(ImportBatch.committed_at.desc()).limit(1))
    h = load_history(db)
    return {
        "base_currency": settings.base_currency,
        "counts": {"accounts": db.scalar(select(func.count()).select_from(Account)),
                   "assets": db.scalar(select(func.count()).select_from(Asset)),
                   "transactions": db.scalar(select(func.count()).select_from(Transaction)),
                   "prices": db.scalar(select(func.count()).select_from(Price)),
                   "valuations": db.scalar(select(func.count()).select_from(Valuation))},
        "fx": [{"currency": c, "last_date": d.isoformat(), "count": n} for c, d, n in fx],
        "fx_missing": sorted(c for c in fx_frankfurter.currencies_in_use(db) if c not in {r[0] for r in fx}),
        "last_price_date": (lambda d: d.isoformat() if d else None)(db.scalar(select(func.max(Price.date)))),
        "last_import": {"id": last_import.id, "filename": last_import.filename,
                        "committed_at": last_import.committed_at.isoformat()} if last_import else None,
        "warnings": h.warnings,
    }


@router.post("/fx/refresh")
def refresh_fx(db: Session = Depends(get_db)):
    return fx_frankfurter.refresh(db)
