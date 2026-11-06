from io import BytesIO


def _setup(client):
    acct = client.post("/api/accounts", json={"name": "Broker", "type": "broker"}).json()
    asset = client.post("/api/assets", json={"name": "Apple", "symbol": "AAPL", "asset_class": "equity"}).json()
    for body in (
        {"type": "deposit", "trade_date": "2025-01-02", "amount": "10000"},
        {"type": "buy", "trade_date": "2025-01-02", "asset_id": asset["id"], "quantity": "10", "price": "100",
         "fees": "1"},
    ):
        r = client.post("/api/transactions", json={"account_id": acct["id"], **body})
        assert r.status_code == 201, r.text
    return acct, asset


def test_manual_entry_and_dashboard(client):
    acct, asset = _setup(client)
    client.post("/api/prices", json={"asset_id": asset["id"], "date": "2025-01-03", "price": "110"})
    d = client.get("/api/dashboard", params={"period": "ALL"}).json()
    s = d["summary"]
    assert s["end_value"] == 10099  # 10 * 110 + 8999 cash
    assert round(s["gain"], 6) == 99
    assert s["cost_basis"] == 1001
    assert {a["asset_class"] for a in d["allocation"]} == {"equity", "cash"}
    holding = next(h for h in d["holdings"] if h["kind"] == "holding")
    assert holding["price_source"] == "market"

    eq = client.get("/api/dashboard", params={"period": "ALL", "asset_class": "equity"}).json()
    assert eq["summary"]["end_value"] == 1100
    assert [h["kind"] for h in eq["holdings"]] == ["holding"]


def test_validation_errors_are_readable(client):
    acct, asset = _setup(client)
    r = client.post("/api/transactions", json={"account_id": acct["id"], "type": "buy", "trade_date": "2025-01-05",
                                               "asset_id": asset["id"], "price": "1"})
    assert r.status_code == 422
    assert "positive quantity" in r.text
    r = client.get("/api/dashboard", params={"period": "2W"})
    assert r.status_code == 422


def test_account_with_transactions_cannot_be_deleted(client):
    acct, _ = _setup(client)
    assert client.delete(f"/api/accounts/{acct['id']}").status_code == 409


def test_asset_detail_and_documents(client):
    acct, asset = _setup(client)
    up = client.post("/api/attachments", data={"asset_id": asset["id"]},
                     files={"file": ("term-sheet.pdf", BytesIO(b"%PDF-1.4 test"), "application/pdf")})
    assert up.status_code == 201, up.text
    detail = client.get(f"/api/assets/{asset['id']}/detail").json()
    assert detail["attachments"][0]["filename"] == "term-sheet.pdf"
    assert detail["lots"][0]["quantity"] == 10
    assert len(detail["transactions"]) == 1
    dl = client.get(f"/api/attachments/{up.json()['id']}/download")
    assert dl.content == b"%PDF-1.4 test"


def test_valuation_marks_value_illiquid_assets(client):
    acct = client.post("/api/accounts", json={"name": "Direct", "type": "direct"}).json()
    s = client.post("/api/assets", json={"name": "Acme SAFE", "asset_class": "startup"}).json()
    client.post("/api/transactions", json={"account_id": acct["id"], "type": "buy", "trade_date": "2024-01-02",
                                           "asset_id": s["id"], "quantity": "1", "price": "25000"})
    client.post("/api/valuations", json={"asset_id": s["id"], "date": "2024-06-01", "price": "50000",
                                         "method": "last_round"})
    d = client.get("/api/dashboard", params={"period": "ALL"}).json()
    assert d["summary"]["end_value"] == 50000
    assert d["summary"]["moic"] == 2
    assert d["holdings"][0]["stale"] is True  # mark is older than 180 days
    illiquid_off = client.get("/api/dashboard", params={"period": "ALL", "include_illiquid": "false"}).json()
    assert illiquid_off["summary"]["end_value"] == 0
