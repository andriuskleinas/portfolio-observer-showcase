"""CRUD for accounts, assets, transactions, valuations, prices and documents (DASH-01, DASH-10)."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (AccountIn, AccountOut, AssetIn, AssetOut, PriceIn, TemplateIn, TransactionIn,
                             TransactionOut, ValuationIn, ValuationOut)
from app.config import settings
from app.db import get_db
from app.models import (Account, Asset, Attachment, ImportTemplate, Price, Transaction, Valuation)
from app.services.portfolio import ensure_portfolio

router = APIRouter(prefix="/api")

MAX_UPLOAD = 25 * 1024 * 1024


def _get(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj


# --- accounts -----------------------------------------------------------------------

@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return db.scalars(select(Account).order_by(Account.name)).all()


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, db: Session = Depends(get_db)):
    acct = Account(portfolio_id=ensure_portfolio(db).id, **body.model_dump())
    db.add(acct)
    db.commit()
    return acct


@router.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountIn, db: Session = Depends(get_db)):
    acct = _get(db, Account, account_id)
    for k, v in body.model_dump().items():
        setattr(acct, k, v)
    db.commit()
    return acct


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acct = _get(db, Account, account_id)
    if db.scalar(select(Transaction.id).where(Transaction.account_id == account_id).limit(1)):
        raise HTTPException(409, "Account has transactions — archive it instead, or delete its transactions first")
    db.delete(acct)
    db.commit()


# --- assets -------------------------------------------------------------------------

@router.get("/assets", response_model=list[AssetOut])
def list_assets(db: Session = Depends(get_db)):
    return db.scalars(select(Asset).order_by(Asset.name)).all()


@router.post("/assets", response_model=AssetOut, status_code=201)
def create_asset(body: AssetIn, db: Session = Depends(get_db)):
    asset = Asset(**body.model_dump(), external_ids={})
    db.add(asset)
    db.commit()
    return asset


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    return _get(db, Asset, asset_id)


@router.put("/assets/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, body: AssetIn, db: Session = Depends(get_db)):
    asset = _get(db, Asset, asset_id)
    for k, v in body.model_dump().items():
        setattr(asset, k, v)
    db.commit()
    return asset


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = _get(db, Asset, asset_id)
    if db.scalar(select(Transaction.id).where(Transaction.asset_id == asset_id).limit(1)):
        raise HTTPException(409, "Asset has transactions — delete them first")
    db.delete(asset)
    db.commit()


# --- transactions -------------------------------------------------------------------

def _tx_out(t: Transaction) -> TransactionOut:
    out = TransactionOut.model_validate(t)
    out.asset_name = t.asset.name if t.asset else None
    out.asset_symbol = t.asset.symbol if t.asset else None
    out.account_name = t.account.name if t.account else None
    return out


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(account_id: int | None = None, asset_id: int | None = None, limit: int = 500,
                      db: Session = Depends(get_db)):
    q = select(Transaction).order_by(Transaction.trade_date.desc(), Transaction.id.desc()).limit(min(limit, 5000))
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if asset_id:
        q = q.where(Transaction.asset_id == asset_id)
    return [_tx_out(t) for t in db.scalars(q).unique()]


def _apply_tx(t: Transaction, body: TransactionIn, db: Session) -> None:
    acct = _get(db, Account, body.account_id)
    asset = _get(db, Asset, body.asset_id) if body.asset_id else None
    data = body.model_dump()
    data["currency"] = body.currency or (asset.currency if asset else acct.currency)
    for k, v in data.items():
        setattr(t, k, v)


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, db: Session = Depends(get_db)):
    t = Transaction(source="manual")
    _apply_tx(t, body, db)
    db.add(t)
    db.commit()
    return _tx_out(t)


@router.put("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, body: TransactionIn, db: Session = Depends(get_db)):
    t = _get(db, Transaction, tx_id)
    _apply_tx(t, body, db)
    db.commit()
    return _tx_out(t)


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Transaction, tx_id))
    db.commit()


# --- valuations and prices -------------------------------------------------------------

@router.get("/valuations", response_model=list[ValuationOut])
def list_valuations(asset_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Valuation).order_by(Valuation.date.desc())
    if asset_id:
        q = q.where(Valuation.asset_id == asset_id)
    return db.scalars(q).all()


@router.post("/valuations", response_model=ValuationOut, status_code=201)
def create_valuation(body: ValuationIn, db: Session = Depends(get_db)):
    asset = _get(db, Asset, body.asset_id)
    v = Valuation(**{**body.model_dump(), "currency": body.currency or asset.currency})
    db.add(v)
    db.commit()
    return v


@router.delete("/valuations/{valuation_id}", status_code=204)
def delete_valuation(valuation_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Valuation, valuation_id))
    db.commit()


@router.post("/prices", status_code=201)
def set_price(body: PriceIn, db: Session = Depends(get_db)):
    """Manual price override (VAL-05)."""
    asset = _get(db, Asset, body.asset_id)
    p = db.scalar(select(Price).where(Price.asset_id == asset.id, Price.date == body.date, Price.source == "manual"))
    if p is None:
        p = Price(asset_id=asset.id, date=body.date, source="manual", currency=body.currency or asset.currency,
                  price=body.price)
        db.add(p)
    else:
        p.price = body.price
    db.commit()
    return {"id": p.id}


# --- documents --------------------------------------------------------------------------

def _att(a: Attachment) -> dict:
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size": a.size,
            "asset_id": a.asset_id, "account_id": a.account_id, "transaction_id": a.transaction_id,
            "notes": a.notes, "uploaded_at": a.uploaded_at.isoformat()}


@router.get("/attachments")
def list_attachments(asset_id: int | None = None, account_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Attachment).order_by(Attachment.uploaded_at.desc())
    if asset_id:
        q = q.where(Attachment.asset_id == asset_id)
    if account_id:
        q = q.where(Attachment.account_id == account_id)
    return [_att(a) for a in db.scalars(q)]


@router.post("/attachments", status_code=201)
async def upload_attachment(file: UploadFile = File(...), asset_id: int | None = Form(None),
                            account_id: int | None = Form(None), transaction_id: int | None = Form(None),
                            notes: str | None = Form(None), db: Session = Depends(get_db)):
    if not (asset_id or account_id or transaction_id):
        raise HTTPException(422, "Attach the document to an asset, account or transaction")
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 25 MB")
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex  # never use the client's filename on disk
    (settings.attachments_dir / stored).write_bytes(content)
    a = Attachment(asset_id=asset_id, account_id=account_id, transaction_id=transaction_id,
                   filename=(file.filename or "document")[:300], stored_name=stored,
                   content_type=file.content_type, size=len(content), notes=notes)
    db.add(a)
    db.commit()
    return _att(a)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    a = _get(db, Attachment, attachment_id)
    path = settings.attachments_dir / a.stored_name
    if not path.is_file():
        raise HTTPException(404, "File is missing from the data folder")
    return FileResponse(path, media_type=a.content_type or "application/octet-stream", filename=a.filename)


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    a = _get(db, Attachment, attachment_id)
    (settings.attachments_dir / a.stored_name).unlink(missing_ok=True)
    db.delete(a)
    db.commit()


# --- saved import mappings ----------------------------------------------------------------

@router.get("/import-templates")
def list_templates(db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "mapping": t.mapping} for t in db.scalars(select(ImportTemplate))]


@router.post("/import-templates", status_code=201)
def save_template(body: TemplateIn, db: Session = Depends(get_db)):
    t = db.scalar(select(ImportTemplate).where(ImportTemplate.name == body.name))
    if t is None:
        t = ImportTemplate(name=body.name, mapping=body.mapping)
        db.add(t)
    else:
        t.mapping = body.mapping
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A template with that name already exists")
    return {"id": t.id, "name": t.name, "mapping": t.mapping}


@router.delete("/import-templates/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, ImportTemplate, template_id))
    db.commit()
