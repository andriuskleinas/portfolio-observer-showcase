"""Shared parsing helpers. Parsers return plain JSON-serializable rows so a preview can be
stored on the import batch and committed later."""

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_DATE_FORMATS = ["%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y",
                 "%d %B %Y", "%d %b %Y", "%m/%d/%y"]


def parse_date(value, fmt: str | None = None) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    candidates = [s]
    for sep in (";", "T", " "):
        if sep in s:
            candidates.append(s.split(sep)[0].strip(", "))
    for c in candidates:
        for f in [fmt] if fmt else _DATE_FORMATS:
            try:
                return datetime.strptime(c, f).date()
            except (ValueError, TypeError):
                continue
    return None


_THOUSANDS_COMMA = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def parse_decimal(value) -> Decimal | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in {"-", "--"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[\s$€£¥()]|[A-Z]{3}$", "", s.strip("()"))
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if _THOUSANDS_COMMA.match(s) else s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if negative else d


def dec_str(d: Decimal | None) -> str | None:
    return None if d is None else format(d.normalize(), "f")


def row_hash(*parts) -> str:
    return hashlib.sha1("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()[:16]


def new_row(n: int, typ: str | None, d: date | None, **kw) -> dict:
    row = {"row": n, "type": typ, "date": d.isoformat() if d else None, "asset": None, "quantity": None,
           "price": None, "amount": None, "currency": None, "counter_amount": None, "counter_currency": None,
           "fees": "0", "fx_rate_to_base": None, "external_id": None, "notes": None, "errors": [], "status": "new"}
    row.update(kw)
    return row
