from datetime import date, timedelta
from decimal import Decimal as D

from app.engine.analytics import Filters, aggregate, holding_rows, metrics, select_keys
from app.engine.ledger import build_history, quantities, trade_observations
from app.engine.market import FxBook, PriceBook
from app.engine.types import AccountInfo, AssetInfo, Observation, Tx

D0 = date(2025, 1, 6)
D1 = D0 + timedelta(days=1)
D2 = D0 + timedelta(days=2)


def run(txs, accounts, assets, prices=(), fx_rates=(), end=D2):
    book = PriceBook(list(prices) + trade_observations(txs))
    return build_history(txs, {a.id: a for a in accounts}, {a.id: a for a in assets}, book,
                         FxBook("USD", fx_rates), end)


def all_metrics(h, filters=Filters()):
    keys = select_keys(h, filters)
    agg = aggregate(h, keys)
    return metrics(h, keys, agg, h.start, h.end), keys


BROKER = AccountInfo(1, "Broker", tracks_cash=True)
DIRECT = AccountInfo(2, "Direct deals", tracks_cash=False)
AAPL = AssetInfo(10, "Apple", "equity", "USD", "AAPL")


def broker_scenario():
    txs = [
        Tx(1, 1, "deposit", D0, amount=D(10000)),
        Tx(2, 1, "buy", D0, asset_id=10, quantity=D(10), price=D(100), fees=D(1)),
        Tx(3, 1, "dividend", D1, asset_id=10, amount=D(10)),
        Tx(4, 1, "sell", D2, asset_id=10, quantity=D(5), price=D(120), fees=D(1)),
    ]
    prices = [(10, Observation(D1, D(110), "market")), (10, Observation(D2, D(120), "market"))]
    return run(txs, [BROKER], [AAPL], prices)


def test_portfolio_value_cash_and_gain():
    h = broker_scenario()
    m, _ = all_metrics(h)
    # 5 shares * 120 + cash (10000 - 1001 + 10 + 599)
    assert m["end_value"] == D(10208)
    assert m["net_flows"] == D(10000)
    assert m["gain"] == D(208)
    assert m["twr"] == D("0.0208")
    assert m["income"] == D(10)


def test_fifo_realized_and_unrealized():
    h = broker_scenario()
    m, keys = all_metrics(h)
    assert m["realized"] == D("98.5")  # 599 proceeds - 500.5 FIFO cost
    row = next(r for r in holding_rows(h, keys, h.start, h.end) if r["kind"] == "holding")
    assert row["quantity"] == D(5)
    assert row["cost_basis"] == D("500.5")
    assert row["unrealized"] == D("99.5")
    # realized + unrealized + income adds up to the total gain
    assert m["realized"] + row["unrealized"] + m["income"] == m["gain"]


def test_holding_only_selection_treats_trades_as_flows():
    h = broker_scenario()
    m, _ = all_metrics(h, Filters(asset_classes={"equity"}))
    assert m["net_flows"] == D(1001) - D(10) - D(599)
    assert m["gain"] == D(208)
    expected = (D(1000) / D(1001)) * (D(1110) / D(1000)) * (D(1199) / D(1100)) - 1
    assert abs(m["twr"] - expected) < D("1e-20")


def test_cash_selection_has_no_external_flows_from_trades():
    h = broker_scenario()
    m, _ = all_metrics(h, Filters(asset_classes={"cash"}))
    assert m["end_value"] == D(9608)


def test_fx_effect_on_foreign_asset():
    asml = AssetInfo(11, "ASML", "equity", "EUR", "ASML")
    txs = [Tx(1, 2, "buy", D0, asset_id=11, quantity=D(10), price=D(100), currency="EUR")]
    fx = [("EUR", D0, D("1.1")), ("EUR", D2, D("1.2"))]
    h = run(txs, [DIRECT], [asml], fx_rates=fx)
    m, _ = all_metrics(h)
    assert m["net_flows"] == D(1100)
    assert m["end_value"] == D(1200)
    assert m["gain"] == D(100)


def test_ownership_share_scales_values_and_flows():
    flat = AssetInfo(20, "Flat", "real_estate", "USD", liquidity="illiquid", valuation_method="manual")
    half = AccountInfo(3, "Co-owned flat", tracks_cash=False, ownership=D("0.5"))
    txs = [Tx(1, 3, "buy", D0, asset_id=20, quantity=D(1), price=D(200000))]
    marks = [(20, Observation(D2, D(300000), "mark"))]
    h = run(txs, [half], [flat], marks)
    m, _ = all_metrics(h)
    assert m["end_value"] == D(150000)
    assert m["gain"] == D(50000)
    assert m["moic"] == D("1.5")


def test_split_keeps_value_and_cost():
    txs = [Tx(1, 2, "buy", D0, asset_id=10, quantity=D(10), price=D(100)),
           Tx(2, 2, "split", D1, asset_id=10, quantity=D(4))]
    prices = [(10, Observation(D1, D(25), "market"))]
    h = run(txs, [DIRECT], [AAPL], prices)
    hs = h.holdings[("h", 2, 10)]
    assert hs.quantity == D(40)
    assert hs.cost_base == D(1000)
    m, _ = all_metrics(h)
    assert m["end_value"] == D(1000)


def test_write_off_realizes_the_full_cost():
    startup = AssetInfo(30, "Acme SAFE", "startup", liquidity="illiquid", valuation_method="manual")
    txs = [Tx(1, 2, "buy", D0, asset_id=30, quantity=D(1), price=D(50000)),
           Tx(2, 2, "write_off", D2, asset_id=30)]
    h = run(txs, [DIRECT], [startup])
    m, _ = all_metrics(h)
    assert m["end_value"] == 0
    assert m["realized"] == D(-50000)
    assert m["moic"] == 0


def test_currency_exchange_spread_is_a_loss_not_a_flow():
    txs = [Tx(1, 1, "deposit", D0, amount=D(1000)),
           Tx(2, 1, "fx", D0, amount=D(1000), currency="USD", counter_amount=D(900), counter_currency="EUR")]
    h = run(txs, [BROKER], [], fx_rates=[("EUR", D0, D("1.1"))])
    m, _ = all_metrics(h)
    assert m["net_flows"] == D(1000)
    assert m["end_value"] == D(990)
    assert m["gain"] == D(-10)


def test_return_of_capital_reduces_cost():
    fund = AssetInfo(40, "VC Fund I", "private_fund", liquidity="illiquid", valuation_method="manual")
    txs = [Tx(1, 2, "capital_call", D0, asset_id=40, amount=D(1000)),
           Tx(2, 2, "return_of_capital", D1, asset_id=40, amount=D(250))]
    h = run(txs, [DIRECT], [fund], [(40, Observation(D2, D(900), "mark"))])
    assert h.holdings[("h", 2, 40)].cost_base == D(750)
    m, _ = all_metrics(h)
    assert m["moic"] == (D(900) + D(250)) / D(1000)


def test_overselling_warns():
    txs = [Tx(1, 2, "buy", D0, asset_id=10, quantity=D(1), price=D(100)),
           Tx(2, 2, "sell", D1, asset_id=10, quantity=D(2), price=D(100))]
    h = run(txs, [DIRECT], [AAPL])
    assert any("more Apple than held" in w for w in h.warnings)


def test_quantities_for_reconciliation():
    txs = [Tx(1, 1, "buy", D0, asset_id=10, quantity=D(10), price=D(1)),
           Tx(2, 1, "split", D1, asset_id=10, quantity=D(2)),
           Tx(3, 1, "sell", D2, asset_id=10, quantity=D(5), price=D(1))]
    assert quantities(txs) == {(1, 10): D(15)}
