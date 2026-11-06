"""Interactive Brokers Flex Query (XML) import (DASH-16).

Reads the sections a Flex Query can contain: Trades, Cash Transactions, Corporate Actions,
Open Positions, Prior Period Positions and Conversion Rates. Field names follow IBKR's
Flex Query reference; unknown sections are ignored. See docs/IBKR_FLEX_SETUP.md.
"""

import re
import xml.etree.ElementTree as ET
from decimal import Decimal

from app.importers.common import dec_str, new_row, parse_date, parse_decimal, row_hash

_CATEGORY_TO_CLASS = {"STK": "equity", "FUND": "fund", "BOND": "fixed_income", "BILL": "fixed_income",
                      "CRYPTO": "crypto", "CMDTY": "commodity"}
_SKIP_DETAIL = {"CLOSED_LOT", "SYMBOL_SUMMARY", "ASSET_SUMMARY", "WASH_SALE", "SUMMARY"}
_SPLIT = re.compile(r"split\s+(\d+(?:\.\d+)?)\s+for\s+(\d+(?:\.\d+)?)", re.IGNORECASE)


class FlexError(ValueError):
    pass


def _asset_ref(el: ET.Element, currency: str | None = None) -> dict:
    cat = (el.get("assetCategory") or "STK").upper()
    symbol = el.get("symbol") or None
    return {"symbol": symbol, "name": el.get("description") or symbol, "isin": el.get("isin") or None,
            "conid": el.get("conid") or None, "asset_class": _CATEGORY_TO_CLASS.get(cat, "other"),
            "sub_class": None if cat in _CATEGORY_TO_CLASS else cat,
            "currency": (el.get("currency") or currency or "USD").upper()}


def _multiplier(el: ET.Element) -> Decimal:
    m = parse_decimal(el.get("multiplier"))
    return m if m and m > 0 else Decimal(1)


def _date(el: ET.Element, *attrs: str):
    for a in attrs:
        d = parse_date(el.get(a))
        if d:
            return d
    return None


def parse_flex(content: bytes, base_currency: str) -> tuple[list[dict], dict]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise FlexError(f"Not a valid Flex Query XML file ({e}). In IBKR, set the Flex Query format to XML.") from e
    if root.tag != "FlexQueryResponse" and root.find(".//FlexStatement") is None:
        raise FlexError("This XML is not an Interactive Brokers Flex Query report")

    warnings: list[str] = []
    account_ids = sorted({s.get("accountId") for s in root.iter("FlexStatement") if s.get("accountId")})
    if len(account_ids) > 1:
        warnings.append(f"Report contains {len(account_ids)} accounts ({', '.join(account_ids)}); all rows go to the selected account")

    # The IBKR account's base currency decides whether its fxRateToBase is usable as ours.
    ibkr_base = None
    info = root.find(".//AccountInformation")
    if info is not None:
        ibkr_base = info.get("currency")
    fx_rates = []
    for cr in root.iter("ConversionRate"):
        to_ccy = cr.get("toCurrency")
        ibkr_base = ibkr_base or to_ccy
        d, rate = parse_date(cr.get("reportDate")), parse_decimal(cr.get("rate"))
        if to_ccy == base_currency and d and rate and cr.get("fromCurrency") != base_currency:
            fx_rates.append({"currency": cr.get("fromCurrency"), "date": d.isoformat(), "rate": dec_str(rate)})
    use_fx = ibkr_base == base_currency

    rows: list[dict] = []
    n = 0

    def add(row: dict) -> None:
        rows.append(row)

    # --- Trades -----------------------------------------------------------------------
    trades = list(root.iter("Trade"))
    has_exec = any((t.get("levelOfDetail") or "").upper() == "EXECUTION" for t in trades)
    for t in trades:
        n += 1
        detail = (t.get("levelOfDetail") or "").upper()
        if detail in _SKIP_DETAIL or (has_exec and detail == "ORDER"):
            continue
        d = _date(t, "tradeDate", "dateTime")
        qty = parse_decimal(t.get("quantity")) or Decimal(0)
        price = parse_decimal(t.get("tradePrice")) or Decimal(0)
        ccy = (t.get("currency") or "USD").upper()
        comm = -(parse_decimal(t.get("ibCommission")) or Decimal(0))
        comm_ccy = (t.get("ibCommissionCurrency") or ccy).upper()
        tid = t.get("transactionID") or t.get("tradeID") or row_hash(d, t.get("symbol"), qty, price)
        fx_rate = dec_str(parse_decimal(t.get("fxRateToBase"))) if use_fx else None
        cat = (t.get("assetCategory") or "STK").upper()

        if cat == "CASH":  # currency conversion, symbol like EUR.USD
            parts = (t.get("symbol") or "").split(".")
            if len(parts) != 2 or d is None:
                add(new_row(n, "fx", d, errors=[f"Unreadable currency trade '{t.get('symbol')}'"], status="error"))
                continue
            first, second = parts[0].upper(), parts[1].upper()
            if qty > 0:  # bought `first`, paid in `second`
                amount, sold, counter, bought = qty * price, second, qty, first
            else:
                amount, sold, counter, bought = -qty, first, -qty * price, second
            add(new_row(n, "fx", d, amount=dec_str(amount), currency=sold, counter_amount=dec_str(counter),
                        counter_currency=bought, external_id=f"ibkr:trade:{tid}",
                        notes=f"{t.get('symbol')} @ {dec_str(price)}"))
            if comm:
                add(new_row(n, "fee", d, amount=dec_str(comm), currency=comm_ccy,
                            external_id=f"ibkr:trade:{tid}:comm", notes="FX commission"))
            continue

        mult = _multiplier(t)
        typ = "buy" if (t.get("buySell") or "").upper().startswith("BUY") or (not t.get("buySell") and qty > 0) else "sell"
        fees = comm if comm_ccy == ccy else Decimal(0)
        errors = [] if d else ["Missing trade date"]
        add(new_row(n, typ, d, asset=_asset_ref(t, ccy), quantity=dec_str(abs(qty)), price=dec_str(price * mult),
                    currency=ccy, fees=dec_str(fees), fx_rate_to_base=fx_rate, external_id=f"ibkr:trade:{tid}",
                    errors=errors, status="error" if errors else "new"))
        if comm and comm_ccy != ccy:
            add(new_row(n, "fee", d, asset=_asset_ref(t, ccy), amount=dec_str(comm), currency=comm_ccy,
                        external_id=f"ibkr:trade:{tid}:comm", notes="Commission"))

    # --- Cash transactions -------------------------------------------------------------
    for c in root.iter("CashTransaction"):
        n += 1
        if (c.get("levelOfDetail") or "").upper() in _SKIP_DETAIL:
            continue
        d = _date(c, "dateTime", "settleDate", "reportDate")
        amt = parse_decimal(c.get("amount")) or Decimal(0)
        ccy = (c.get("currency") or "USD").upper()
        kind = (c.get("type") or "").strip()
        k = kind.lower()
        tid = c.get("transactionID") or row_hash(d, kind, c.get("symbol"), amt)
        has_asset = bool(c.get("symbol") or c.get("conid"))
        asset = _asset_ref(c, ccy) if has_asset else None
        fx_rate = dec_str(parse_decimal(c.get("fxRateToBase"))) if use_fx else None
        common = dict(currency=ccy, fx_rate_to_base=fx_rate, external_id=f"ibkr:cash:{tid}",
                      notes=c.get("description") or kind)

        if "dividend" in k:  # Dividends, Payment In Lieu Of Dividends
            add(new_row(n, "dividend", d, asset=asset, amount=dec_str(amt), **common))
        elif "withholding" in k:
            add(new_row(n, "tax", d, asset=asset, amount=dec_str(-amt), **common))
        elif "interest" in k:
            add(new_row(n, "interest" if amt >= 0 else "fee", d, asset=asset, amount=dec_str(abs(amt)), **common))
        elif "deposit" in k or "withdrawal" in k:
            add(new_row(n, "deposit" if amt >= 0 else "withdrawal", d, amount=dec_str(abs(amt)), **common))
        elif "fee" in k or "commission" in k:
            add(new_row(n, "fee", d, asset=asset, amount=dec_str(-amt), **common))
        else:
            add(new_row(n, None, d, amount=dec_str(amt), errors=[f"Unsupported cash transaction type '{kind}'"],
                        status="error", **common))

    # --- Corporate actions --------------------------------------------------------------
    seen_splits = set()
    for ca in root.iter("CorporateAction"):
        n += 1
        if (ca.get("levelOfDetail") or "").upper() in _SKIP_DETAIL:
            continue
        d = _date(ca, "reportDate", "dateTime")
        desc = ca.get("description") or ""
        m = _SPLIT.search(desc)
        if ca.get("type") in ("FS", "RS") and m:
            key = (ca.get("conid") or ca.get("symbol"), d)
            if key in seen_splits:
                continue
            seen_splits.add(key)
            ratio = Decimal(m.group(1)) / Decimal(m.group(2))
            aid = ca.get("actionID") or ca.get("transactionID") or row_hash(*key)
            add(new_row(n, "split", d, asset=_asset_ref(ca), quantity=dec_str(ratio),
                        currency=(ca.get("currency") or "USD").upper(), external_id=f"ibkr:ca:{aid}", notes=desc))
        else:
            warnings.append(f"Corporate action needs manual entry: {desc or ca.get('type')} ({d})")

    # --- Positions and prices --------------------------------------------------------------
    positions, prices = [], []
    for p in root.iter("OpenPosition"):
        if (p.get("levelOfDetail") or "SUMMARY").upper() not in ("SUMMARY", ""):
            continue
        d = _date(p, "reportDate")
        mark = parse_decimal(p.get("markPrice"))
        qty = parse_decimal(p.get("position"))
        if d is None or qty is None:
            continue
        ref = _asset_ref(p)
        mult = _multiplier(p)
        positions.append({"asset": ref, "quantity": dec_str(qty), "date": d.isoformat(),
                          "mark_price": dec_str(mark * mult) if mark is not None else None})
        if mark is not None:
            prices.append({"asset": ref, "date": d.isoformat(), "price": dec_str(mark * mult), "currency": ref["currency"]})
    for p in root.iter("PriorPeriodPosition"):
        d = _date(p, "date", "reportDate")
        price = parse_decimal(p.get("price"))
        if d and price is not None:
            ref = _asset_ref(p)
            prices.append({"asset": ref, "date": d.isoformat(), "price": dec_str(price * _multiplier(p)),
                           "currency": ref["currency"]})

    if not rows and not positions:
        warnings.append("No trades, cash transactions or positions found — check the sections selected in the Flex Query")

    extras = {"prices": prices, "fx_rates": fx_rates, "positions": positions, "valuations": [],
              "warnings": warnings, "account_ref": account_ids[0] if account_ids else None, "ibkr_base": ibkr_base}
    return rows, extras
