"""Generic CSV import with a column mapping (DASH-03). Also covers Notion database exports
(DASH-15), which are usually lists of holdings rather than transactions: a row with an
amount but no quantity becomes a buy of 1 unit at that amount, and an optional current
value column becomes a valuation mark."""

import csv
import io

from app.importers.common import dec_str, new_row, parse_date, parse_decimal, row_hash
from app.taxonomy import ASSET_CLASSES, TX_TYPES

FIELDS = ["date", "type", "symbol", "name", "isin", "asset_class", "quantity", "price", "amount", "currency",
          "fees", "external_id", "notes", "value", "value_date", "counter_amount", "counter_currency"]

_TYPE_WORDS = [
    ("transfer in", "transfer_in"), ("transfer out", "transfer_out"), ("return of capital", "return_of_capital"),
    ("capital call", "capital_call"), ("write", "write_off"), ("withdraw", "withdrawal"), ("deposit", "deposit"),
    ("buy", "buy"), ("bought", "buy"), ("purchase", "buy"), ("invest", "buy"), ("sell", "sell"), ("sold", "sell"),
    ("div", "dividend"), ("interest", "interest"), ("coupon", "coupon"), ("rent", "rent"),
    ("distribution", "distribution"), ("commission", "fee"), ("fee", "fee"), ("tax", "tax"), ("split", "split"),
    ("staking", "staking_reward"), ("airdrop", "airdrop"), ("expense", "expense"),
]

_ASSET_TYPES = {k for k, v in TX_TYPES.items() if v["asset"] == "required"}


def decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def read_rows(content: bytes) -> tuple[list[str], list[dict]]:
    text = decode(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = [r for r in reader if any((v or "").strip() for v in r.values())]
    return [h for h in (reader.fieldnames or []) if h], rows


def normalize_type(raw: str | None, type_map: dict[str, str], default: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return default
    s = str(raw).strip()
    for k, v in type_map.items():
        if k.lower() == s.lower():
            return v
    low = s.lower().replace("_", " ")
    if s.lower() in TX_TYPES:
        return s.lower()
    for word, typ in _TYPE_WORDS:
        if word in low:
            return typ
    return None


def parse_csv(content: bytes, mapping: dict) -> tuple[list[dict], dict]:
    cols: dict[str, str] = mapping.get("columns", {})
    defaults: dict = mapping.get("defaults", {})
    type_map: dict = mapping.get("type_map", {})
    date_fmt = mapping.get("date_format") or None
    _, raw_rows = read_rows(content)

    def get(r: dict, field: str):
        col = cols.get(field)
        return r.get(col) if col else None

    rows, valuations = [], []
    for n, r in enumerate(raw_rows, start=2):  # row 1 is the header
        d = parse_date(get(r, "date"), date_fmt)
        typ = normalize_type(get(r, "type"), type_map, defaults.get("type"))
        qty, price, amount = parse_decimal(get(r, "quantity")), parse_decimal(get(r, "price")), parse_decimal(get(r, "amount"))
        fees = parse_decimal(get(r, "fees"))
        currency = (get(r, "currency") or defaults.get("currency") or "USD").strip().upper()[:3]
        symbol, name = (get(r, "symbol") or "").strip() or None, (get(r, "name") or "").strip() or None
        asset_class = (get(r, "asset_class") or "").strip().lower().replace(" ", "_") or defaults.get("asset_class") or "equity"
        if asset_class not in ASSET_CLASSES:
            asset_class = defaults.get("asset_class") or "other"

        errors = []
        if d is None:
            errors.append("Missing or unreadable date")
        if typ is None:
            errors.append(f"Unknown transaction type '{get(r, 'type')}'")

        # Signed quantities: a negative buy is a sell
        if qty is not None and qty < 0 and typ in ("buy", "sell"):
            typ, qty = "sell", -qty
        if amount is not None and amount < 0 and typ not in ("buy", "sell", None):
            amount = -amount

        if typ in ("buy", "sell"):
            if qty is None and amount is not None:
                qty, price = parse_decimal("1"), abs(amount)
            elif qty is not None and price is None and amount is not None and qty:
                price = abs(amount) / qty
            if qty is None or price is None:
                errors.append("Buy/sell needs quantity and price (or an amount)")

        asset = None
        if symbol or name:
            asset = {"symbol": symbol, "name": name or symbol, "isin": (get(r, "isin") or "").strip() or None,
                     "conid": None, "asset_class": asset_class, "currency": currency}
        elif typ in _ASSET_TYPES:
            errors.append("Missing asset name or symbol")

        ext = (get(r, "external_id") or "").strip() or None
        ext = f"csv:{ext}" if ext else "csv:" + row_hash(d, typ, symbol or name, qty, price, amount)
        rows.append(new_row(
            n, typ, d, asset=asset, quantity=dec_str(qty), price=dec_str(price), amount=dec_str(amount),
            currency=currency, fees=dec_str(abs(fees)) if fees else "0",
            counter_amount=dec_str(parse_decimal(get(r, "counter_amount"))),
            counter_currency=((get(r, "counter_currency") or "").strip().upper() or None),
            external_id=ext, notes=(get(r, "notes") or "").strip() or None, errors=errors,
            status="error" if errors else "new"))

        value = parse_decimal(get(r, "value"))
        if value is not None and asset and qty:
            vd = parse_date(get(r, "value_date"), date_fmt) or d
            if vd:
                valuations.append({"asset": asset, "date": vd.isoformat(), "price": dec_str(value / qty),
                                   "currency": currency})

    return rows, {"valuations": valuations, "prices": [], "fx_rates": [], "positions": [], "warnings": []}
