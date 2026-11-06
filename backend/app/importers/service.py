"""Preview, commit and roll back import batches (DASH-03, DASH-04)."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.engine.ledger import quantities
from app.engine.types import Tx
from app.importers.csv_generic import parse_csv
from app.importers.ibkr_flex import parse_flex
from app.models import Account, Asset, FxRate, ImportBatch, Price, Transaction, Valuation, utcnow
from app.taxonomy import ASSET_CLASSES


class ImportError_(ValueError):
    pass


class AssetIndex:
    """Matches imported asset references to existing assets: IBKR conid, then ISIN, then
    symbol + currency, then exact name."""

    def __init__(self, assets: list[Asset]):
        self.by_conid, self.by_isin, self.by_symbol, self.by_name = {}, {}, {}, {}
        for a in assets:
            self.add(a)

    def add(self, a: Asset) -> None:
        conid = (a.external_ids or {}).get("ibkr_conid")
        if conid:
            self.by_conid[str(conid)] = a
        if a.isin:
            self.by_isin[a.isin.upper()] = a
        if a.symbol:
            self.by_symbol[(a.symbol.upper(), a.currency)] = a
        self.by_name[a.name.strip().lower()] = a

    def find(self, ref: dict) -> Asset | None:
        if ref.get("conid") and str(ref["conid"]) in self.by_conid:
            return self.by_conid[str(ref["conid"])]
        if ref.get("isin") and ref["isin"].upper() in self.by_isin:
            return self.by_isin[ref["isin"].upper()]
        if ref.get("symbol") and (ref["symbol"].upper(), ref.get("currency")) in self.by_symbol:
            return self.by_symbol[(ref["symbol"].upper(), ref.get("currency"))]
        if ref.get("name") and ref["name"].strip().lower() in self.by_name:
            return self.by_name[ref["name"].strip().lower()]
        return None


def _ref_key(ref: dict) -> str:
    return ref.get("conid") or ref.get("isin") or f"{ref.get('symbol') or ref.get('name')}|{ref.get('currency')}"


def create_asset(db: Session, ref: dict) -> Asset:
    cls = ref.get("asset_class") if ref.get("asset_class") in ASSET_CLASSES else "other"
    meta = ASSET_CLASSES[cls]
    a = Asset(name=ref.get("name") or ref.get("symbol") or "Unnamed asset", asset_class=cls,
              sub_class=ref.get("sub_class"), symbol=ref.get("symbol"), isin=ref.get("isin"),
              external_ids={"ibkr_conid": ref["conid"]} if ref.get("conid") else {},
              currency=(ref.get("currency") or settings.base_currency).upper(),
              liquidity=meta["liquidity"], valuation_method=meta["valuation"], tags=[])
    db.add(a)
    db.flush()
    return a


def preview(db: Session, kind: str, filename: str | None, content: bytes, account_id: int | None,
            mapping: dict | None) -> ImportBatch:
    if kind == "ibkr_flex":
        rows, extras = parse_flex(content, settings.base_currency)
    elif kind == "csv":
        if not mapping or not mapping.get("columns"):
            raise ImportError_("CSV import needs a column mapping")
        rows, extras = parse_csv(content, mapping)
    else:
        raise ImportError_(f"Unknown import kind '{kind}'")

    if account_id is None and extras.get("account_ref"):
        acct = db.scalar(select(Account).where(Account.external_ref == extras["account_ref"]))
        account_id = acct.id if acct else None
    if account_id is None or db.get(Account, account_id) is None:
        raise ImportError_("Choose the account these records belong to")

    existing = set(db.scalars(select(Transaction.external_id).where(
        Transaction.account_id == account_id, Transaction.external_id.is_not(None))))
    index = AssetIndex(list(db.scalars(select(Asset))))
    seen = set()
    new_assets: dict[str, dict] = {}
    for r in rows:
        if r["status"] == "error":
            continue
        if r["external_id"] in existing or r["external_id"] in seen:
            r["status"] = "duplicate"
            continue
        seen.add(r["external_id"])
        if r["asset"]:
            match = index.find(r["asset"])
            r["asset_match"] = {"id": match.id, "name": match.name} if match else None
            if not match:
                new_assets[_ref_key(r["asset"])] = r["asset"]

    batch = ImportBatch(kind=kind, filename=filename, account_id=account_id, status="preview",
                        payload={"rows": rows, "extras": extras, "mapping": mapping})
    batch.summary = _summary(rows, extras, new_assets)
    batch.summary["reconciliation"] = _reconcile(db, account_id, rows, extras.get("positions", []), index)
    db.add(batch)
    db.commit()
    return batch


def _summary(rows: list[dict], extras: dict, new_assets: dict) -> dict:
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    return {"new": counts["new"], "duplicate": counts["duplicate"], "error": counts["error"],
            "new_assets": list(new_assets.values()), "prices": len(extras.get("prices", [])),
            "fx_rates": len(extras.get("fx_rates", [])), "valuations": len(extras.get("valuations", [])),
            "warnings": extras.get("warnings", [])}


def _to_tx(r: dict, account_id: int, asset_id: int | None, tx_id: int) -> Tx:
    def dec(v):
        return Decimal(v) if v is not None else None

    return Tx(id=tx_id, account_id=account_id, type=r["type"], date=date.fromisoformat(r["date"]),
              asset_id=asset_id, quantity=dec(r["quantity"]), price=dec(r["price"]), amount=dec(r["amount"]),
              currency=r["currency"] or "USD")


def _reconcile(db: Session, account_id: int, rows: list[dict], positions: list[dict], index: AssetIndex) -> list[dict]:
    """Compare the broker's reported positions with what the ledger will hold after import."""
    if not positions:
        return []
    temp_ids: dict[str, int] = {}

    def asset_id_for(ref: dict) -> int:
        match = index.find(ref)
        if match:
            return match.id
        return temp_ids.setdefault(_ref_key(ref), -(len(temp_ids) + 1))

    txs = [_to_tx({"type": t.type, "date": t.trade_date.isoformat(), "quantity": t.quantity, "price": t.price,
                   "amount": t.amount, "currency": t.currency}, account_id, t.asset_id, t.id)
           for t in db.scalars(select(Transaction).where(Transaction.account_id == account_id))]
    for i, r in enumerate(rows):
        if r["status"] == "new" and r["asset"] and r["date"]:
            txs.append(_to_tx(r, account_id, asset_id_for(r["asset"]), 10**9 + i))
    held = quantities(txs)
    out = []
    for p in positions:
        aid = asset_id_for(p["asset"])
        ours = held.get((account_id, aid), Decimal(0))
        reported = Decimal(p["quantity"])
        out.append({"symbol": p["asset"].get("symbol"), "name": p["asset"].get("name"), "reported": p["quantity"],
                    "computed": format(ours.normalize(), "f"), "date": p["date"], "match": ours == reported})
    return out


def commit(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ImportError_("Import not found")
    if batch.status != "preview":
        raise ImportError_(f"Import is already {batch.status}")
    rows, extras = batch.payload["rows"], batch.payload["extras"]
    index = AssetIndex(list(db.scalars(select(Asset))))
    existing = set(db.scalars(select(Transaction.external_id).where(
        Transaction.account_id == batch.account_id, Transaction.external_id.is_not(None))))
    created: list[int] = []

    def resolve(ref: dict | None) -> int | None:
        if not ref:
            return None
        a = index.find(ref)
        if a is None:
            a = create_asset(db, ref)
            index.add(a)
            created.append(a.id)
        return a.id

    n_tx = 0
    for r in rows:
        if r["status"] != "new" or r["external_id"] in existing:
            continue
        existing.add(r["external_id"])
        db.add(Transaction(
            account_id=batch.account_id, asset_id=resolve(r["asset"]), type=r["type"],
            trade_date=date.fromisoformat(r["date"]), quantity=r["quantity"], price=r["price"], amount=r["amount"],
            currency=r["currency"] or settings.base_currency, counter_amount=r["counter_amount"],
            counter_currency=r["counter_currency"], fees=r["fees"] or "0", fx_rate_to_base=r["fx_rate_to_base"],
            external_id=r["external_id"], import_batch_id=batch.id, source="import", notes=r["notes"]))
        n_tx += 1

    # Prices only for assets that exist or arrive with this import — a position with no
    # transactions shows up in reconciliation instead of creating an empty asset.
    row_refs = {_ref_key(r["asset"]) for r in rows if r["asset"] and r["status"] == "new"}
    n_prices = 0
    for p in extras.get("prices", []):
        if index.find(p["asset"]) is None and _ref_key(p["asset"]) not in row_refs:
            continue
        aid = resolve(p["asset"])
        d = date.fromisoformat(p["date"])
        existing_price = db.scalar(select(Price).where(Price.asset_id == aid, Price.date == d, Price.source == "ibkr"))
        if existing_price:
            existing_price.price = Decimal(p["price"])
        else:
            db.add(Price(asset_id=aid, date=d, price=p["price"], currency=p["currency"], source="ibkr",
                         import_batch_id=batch.id))
        n_prices += 1

    n_fx = 0
    for f in extras.get("fx_rates", []):
        d = date.fromisoformat(f["date"])
        if not db.scalar(select(FxRate).where(FxRate.currency == f["currency"], FxRate.base == settings.base_currency,
                                              FxRate.date == d)):
            db.add(FxRate(currency=f["currency"], base=settings.base_currency, date=d, rate=f["rate"], source="ibkr"))
            n_fx += 1

    n_val = 0
    for v in extras.get("valuations", []):
        db.add(Valuation(asset_id=resolve(v["asset"]), date=date.fromisoformat(v["date"]), price=v["price"],
                         currency=v["currency"], method="own_estimate", source=f"import:{batch.id}",
                         notes=f"Imported from {batch.filename or 'CSV'}"))
        n_val += 1

    batch.status = "committed"
    batch.committed_at = utcnow()
    batch.summary = {**batch.summary, "committed": {"transactions": n_tx, "assets_created": created,
                                                    "prices": n_prices, "fx_rates": n_fx, "valuations": n_val}}
    db.commit()
    return batch


def rollback(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ImportError_("Import not found")
    if batch.status != "committed":
        raise ImportError_("Only committed imports can be rolled back")
    db.execute(delete(Transaction).where(Transaction.import_batch_id == batch.id))
    db.execute(delete(Price).where(Price.import_batch_id == batch.id))
    db.execute(delete(Valuation).where(Valuation.source == f"import:{batch.id}"))
    for aid in batch.summary.get("committed", {}).get("assets_created", []):
        still_used = db.scalar(select(Transaction.id).where(Transaction.asset_id == aid).limit(1))
        if still_used is None:
            asset = db.get(Asset, aid)
            if asset:
                db.delete(asset)
    batch.status = "rolled_back"
    db.commit()
    return batch
