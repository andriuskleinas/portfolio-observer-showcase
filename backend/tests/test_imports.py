import json
from decimal import Decimal as D
from pathlib import Path

from app.importers.common import parse_date, parse_decimal
from app.importers.csv_generic import parse_csv
from app.importers.ibkr_flex import parse_flex

FIXTURE = (Path(__file__).parent / "fixtures" / "ibkr_flex_sample.xml").read_bytes()


def test_parse_numbers_and_dates():
    assert parse_decimal("1,234.56") == D("1234.56")
    assert parse_decimal("1.234,56") == D("1234.56")
    assert parse_decimal("1,5") == D("1.5")
    assert parse_decimal("(250.00)") == D("-250.00")
    assert parse_decimal("$ 25,000") == D("25000")
    assert parse_date("20240103").isoformat() == "2024-01-03"
    assert parse_date("2024-01-03;101500").isoformat() == "2024-01-03"
    assert parse_date("January 5, 2024").isoformat() == "2024-01-05"


def test_flex_parses_each_section():
    rows, extras = parse_flex(FIXTURE, "USD")
    by_ext = {r["external_id"]: r for r in rows}
    # executions only: the ORDER and CLOSED_LOT copies of the AAPL buy are skipped
    buys = [r for r in rows if r["type"] == "buy"]
    assert len(buys) == 2
    aapl = by_ext["ibkr:trade:5001"]
    assert (aapl["quantity"], aapl["price"], aapl["fees"]) == ("10", "150", "1")
    assert aapl["asset"]["conid"] == "265598"
    sell = by_ext["ibkr:trade:5004"]
    assert sell["type"] == "sell" and sell["quantity"] == "5"
    fx = by_ext["ibkr:trade:5002"]
    assert (fx["type"], fx["currency"], fx["amount"], fx["counter_currency"], fx["counter_amount"]) == \
        ("fx", "USD", "1090", "EUR", "1000")
    assert by_ext["ibkr:trade:5002:comm"]["type"] == "fee"
    asml = by_ext["ibkr:trade:5003"]
    assert asml["currency"] == "EUR" and asml["fees"] == "1.5" and asml["fx_rate_to_base"] == "1.0912"
    assert by_ext["ibkr:cash:6001"]["type"] == "deposit"
    assert by_ext["ibkr:cash:6002"]["type"] == "dividend"
    assert (by_ext["ibkr:cash:6003"]["type"], by_ext["ibkr:cash:6003"]["amount"]) == ("tax", "0.36")
    assert by_ext["ibkr:cash:6004"]["type"] == "interest"
    assert (by_ext["ibkr:cash:6005"]["type"], by_ext["ibkr:cash:6005"]["amount"]) == ("fee", "10")
    assert by_ext["ibkr:cash:6006"]["status"] == "error"
    splits = [r for r in rows if r["type"] == "split"]
    assert len(splits) == 1 and splits[0]["quantity"] == "2"
    assert any("manual entry" in w for w in extras["warnings"])
    assert {p["asset"]["symbol"] for p in extras["positions"]} == {"AAPL", "ASML"}
    assert len(extras["prices"]) == 3
    assert extras["fx_rates"][0] == {"currency": "EUR", "date": "2024-01-04", "rate": "1.0945"}
    assert extras["account_ref"] == "U0000001"


def test_flex_ignores_fx_rate_when_ibkr_base_differs():
    rows, _ = parse_flex(FIXTURE, "EUR")
    assert all(r["fx_rate_to_base"] is None for r in rows)


def test_csv_holdings_list_like_notion():
    content = (
        "Company,Invested on,Amount invested,Instrument,Current value\n"
        "Northwind Robotics,\"March 3, 2023\",\"$25,000\",startup,\"$60,000\"\n"
        "Lumen Health,2023-05-10,40000,startup,\n"
        ",2023-06-01,5000,startup,\n"
    ).encode()
    mapping = {"columns": {"name": "Company", "date": "Invested on", "amount": "Amount invested",
                           "asset_class": "Instrument", "value": "Current value"},
               "defaults": {"type": "buy", "currency": "USD"}}
    rows, extras = parse_csv(content, mapping)
    assert rows[0]["type"] == "buy" and rows[0]["quantity"] == "1" and rows[0]["price"] == "25000"
    assert rows[0]["asset"]["asset_class"] == "startup"
    assert rows[0]["date"] == "2023-03-03"
    assert rows[2]["status"] == "error"  # no company name
    assert extras["valuations"] == [{"asset": rows[0]["asset"], "date": "2023-03-03", "price": "60000",
                                     "currency": "USD"}]


def test_ibkr_import_preview_commit_rollback(client):
    acct = client.post("/api/accounts", json={"name": "IBKR", "type": "broker", "external_ref": "U0000001"}).json()
    res = client.post("/api/imports", data={"kind": "ibkr_flex"},
                      files={"file": ("flex.xml", FIXTURE, "application/xml")})
    assert res.status_code == 201, res.text
    batch = res.json()
    assert batch["account_id"] == acct["id"]  # matched by IBKR account id
    s = batch["summary"]
    assert s["error"] == 1 and s["new"] > 0
    recon = {r["symbol"]: r for r in s["reconciliation"]}
    assert recon["AAPL"]["match"] is True  # 10 bought, 5 sold, split 2:1 -> 10
    assert recon["ASML"]["match"] is False  # report says 2, trades say 1

    res = client.post(f"/api/imports/{batch['id']}/commit")
    assert res.status_code == 200, res.text
    committed = res.json()["summary"]["committed"]
    assert committed["transactions"] == s["new"]
    assert len(committed["assets_created"]) == 2

    # importing the same file again finds only duplicates
    again = client.post("/api/imports", data={"kind": "ibkr_flex", "account_id": acct["id"]},
                        files={"file": ("flex.xml", FIXTURE, "application/xml")}).json()
    assert again["summary"]["new"] == 0 and again["summary"]["duplicate"] == s["new"]

    dash = client.get("/api/dashboard", params={"period": "ALL"}).json()
    assert {h["symbol"] for h in dash["holdings"] if h["kind"] == "holding"} == {"AAPL", "ASML"}

    assert client.post(f"/api/imports/{batch['id']}/rollback").status_code == 200
    assert client.get("/api/transactions").json() == []
    assert client.get("/api/assets").json() == []


def test_csv_import_with_mapping(client):
    acct = client.post("/api/accounts", json={"name": "Direct deals", "type": "direct"}).json()
    assert acct["tracks_cash"] is False
    content = b"Company,Date,Amount\nNorthwind,2024-01-10,25000\n"
    inspect = client.post("/api/imports/inspect", files={"file": ("n.csv", content, "text/csv")}).json()
    assert inspect["guess"]["columns"] == {"name": "Company", "date": "Date", "amount": "Amount"}
    res = client.post("/api/imports", data={"kind": "csv", "account_id": acct["id"],
                                            "mapping": json.dumps(inspect["guess"])},
                      files={"file": ("n.csv", content, "text/csv")})
    assert res.status_code == 201, res.text
    client.post(f"/api/imports/{res.json()['id']}/commit")
    asset = client.get("/api/assets").json()[0]
    assert asset["asset_class"] == "startup" and asset["valuation_method"] == "manual"
