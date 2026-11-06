"""Import preview / commit / rollback endpoints (DASH-03, DASH-04, DASH-15, DASH-16)."""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.importers import service
from app.importers.csv_generic import FIELDS, read_rows
from app.importers.ibkr_flex import FlexError
from app.models import Account, ImportBatch
from app.providers import fx_frankfurter

router = APIRouter(prefix="/api")

MAX_IMPORT = 20 * 1024 * 1024

_SYNONYMS = {
    "date": ["date", "trade date", "transaction date", "invested on", "investment date", "settlement date"],
    "type": ["type", "action", "transaction type", "activity"],
    "symbol": ["symbol", "ticker"],
    "name": ["name", "company", "security", "asset", "investment", "description", "holding"],
    "isin": ["isin"],
    "asset_class": ["asset class", "class", "category", "instrument", "asset type"],
    "quantity": ["quantity", "qty", "shares", "units"],
    "price": ["price", "unit price", "price per share", "share price"],
    "amount": ["amount", "total", "invested", "amount invested", "net amount", "investment amount", "check size"],
    "currency": ["currency", "ccy"],
    "fees": ["fees", "fee", "commission"],
    "value": ["current value", "valuation", "market value", "fair value", "value"],
    "value_date": ["valuation date", "value date", "as of", "last valued"],
    "notes": ["notes", "note", "comment", "memo"],
    "external_id": ["id", "transaction id", "reference"],
}


def guess_mapping(headers: list[str]) -> dict:
    norm = {h: h.strip().lower().replace("_", " ") for h in headers}
    cols, used = {}, set()
    for field, names in _SYNONYMS.items():
        for name in names:
            hit = next((h for h, n in norm.items() if n == name and h not in used), None)
            if hit:
                cols[field] = hit
                used.add(hit)
                break
    return {"columns": cols, "defaults": {"type": None if "type" in cols else "buy", "currency": "USD",
                                          "asset_class": "startup"}, "type_map": {}, "date_format": None}


def _batch_out(b: ImportBatch, db: Session, rows_limit: int = 1000) -> dict:
    acct = db.get(Account, b.account_id) if b.account_id else None
    rows = (b.payload or {}).get("rows", [])
    return {"id": b.id, "kind": b.kind, "filename": b.filename, "status": b.status,
            "account_id": b.account_id, "account": acct.name if acct else None,
            "created_at": b.created_at.isoformat(), "committed_at": b.committed_at.isoformat() if b.committed_at else None,
            "summary": b.summary, "rows": rows[:rows_limit], "row_count": len(rows)}


@router.post("/imports/inspect")
async def inspect_csv(file: UploadFile = File(...)):
    """Headers, sample rows and a guessed mapping for the CSV mapping wizard."""
    content = await file.read()
    headers, rows = read_rows(content)
    if not headers:
        raise HTTPException(422, "Couldn't find a header row in this CSV")
    return {"headers": headers, "sample": rows[:5], "row_count": len(rows), "fields": FIELDS,
            "guess": guess_mapping(headers)}


@router.post("/imports", status_code=201)
async def create_preview(kind: str = Form(...), account_id: int | None = Form(None), mapping: str | None = Form(None),
                         file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    if len(content) > MAX_IMPORT:
        raise HTTPException(413, "File is larger than 20 MB")
    try:
        parsed_mapping = json.loads(mapping) if mapping else None
    except json.JSONDecodeError:
        raise HTTPException(422, "Mapping is not valid JSON")
    try:
        batch = service.preview(db, kind, file.filename, content, account_id, parsed_mapping)
    except (service.ImportError_, FlexError) as e:
        raise HTTPException(422, str(e))
    return _batch_out(batch, db)


@router.get("/imports")
def list_imports(db: Session = Depends(get_db)):
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(100))
    return [{k: v for k, v in _batch_out(b, db, 0).items() if k != "rows"} for b in batches]


@router.get("/imports/{batch_id}")
def get_import(batch_id: int, db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(404, "Import not found")
    return _batch_out(b, db)


def _refresh_fx_in_background() -> None:
    db = SessionLocal()
    try:
        fx_frankfurter.refresh(db)
    finally:
        db.close()


@router.post("/imports/{batch_id}/commit")
def commit_import(batch_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        b = service.commit(db, batch_id)
    except service.ImportError_ as e:
        raise HTTPException(409, str(e))
    background.add_task(_refresh_fx_in_background)
    return _batch_out(b, db, 0)


@router.post("/imports/{batch_id}/rollback")
def rollback_import(batch_id: int, db: Session = Depends(get_db)):
    try:
        b = service.rollback(db, batch_id)
    except service.ImportError_ as e:
        raise HTTPException(409, str(e))
    return _batch_out(b, db, 0)


@router.delete("/imports/{batch_id}", status_code=204)
def discard_preview(batch_id: int, db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(404, "Import not found")
    if b.status != "preview":
        raise HTTPException(409, "Only previews can be discarded; roll back committed imports instead")
    db.delete(b)
    db.commit()
