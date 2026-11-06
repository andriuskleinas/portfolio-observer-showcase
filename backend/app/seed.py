"""Demo portfolio with fake data (OSS-02).

    PT_DATA_DIR=../data/demo python -m app.seed

Refuses to touch a database that already has transactions.
"""

import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.main import run_migrations
from app.models import Account, Asset, FxRate, Price, Transaction, Valuation
from app.services.portfolio import ensure_portfolio

D = Decimal
CENT = D("0.01")


def q2(x) -> Decimal:
    return D(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def walk(rng: random.Random, start: float, days: list[date], drift: float, vol: float) -> dict[date, Decimal]:
    out, p = {}, start
    for d in days:
        p *= math.exp((drift - vol * vol / 2) / 252 + vol / math.sqrt(252) * rng.gauss(0, 1))
        out[d] = q2(p)
    return out


def seed(years: int = 3) -> None:
    run_migrations()
    db = SessionLocal()
    if db.scalar(select(Transaction.id).limit(1)):
        raise SystemExit("This database already has transactions; point PT_DATA_DIR at an empty folder for the demo.")
    pf = ensure_portfolio(db)
    rng = random.Random(42)
    today = date.today()
    start = today - timedelta(days=365 * years)
    all_days = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    weekdays = [d for d in all_days if d.weekday() < 5]

    def acct(**kw):
        a = Account(portfolio_id=pf.id, **kw)
        db.add(a)
        return a

    ibkr = acct(name="Interactive Brokers", institution="Interactive Brokers", type="broker", currency="USD",
                tracks_cash=True, external_ref="U0000001")
    direct = acct(name="Direct startup deals", type="direct", currency="USD", tracks_cash=False)
    flat_acct = acct(name="Riverside flat (50%)", type="property", currency="USD", tracks_cash=False,
                     ownership_pct=D("0.5"))
    wallet = acct(name="Cold wallet", type="wallet", currency="USD", tracks_cash=False)

    def asset(**kw):
        a = Asset(external_ids={}, tags=[], **kw)
        db.add(a)
        return a

    specs = {
        "VTI": dict(name="Vanguard Total Stock Market ETF", asset_class="equity", currency="USD", sector="Broad market",
                    start=210, drift=0.09, vol=0.16),
        "AAPL": dict(name="Apple Inc.", asset_class="equity", currency="USD", sector="Technology",
                     start=165, drift=0.12, vol=0.27),
        "MSFT": dict(name="Microsoft Corp.", asset_class="equity", currency="USD", sector="Technology",
                     start=280, drift=0.13, vol=0.25),
        "ASML": dict(name="ASML Holding N.V.", asset_class="equity", currency="EUR", sector="Semiconductors",
                     start=610, drift=0.10, vol=0.33),
        "BND": dict(name="Vanguard Total Bond Market ETF", asset_class="fixed_income", currency="USD",
                    sector="Bonds", start=74, drift=0.02, vol=0.06),
        "BTC": dict(name="Bitcoin", asset_class="crypto", currency="USD", sector=None,
                    start=27000, drift=0.35, vol=0.60),
    }
    listed, series = {}, {}
    for sym, s in specs.items():
        a = asset(name=s["name"], asset_class=s["asset_class"], symbol=sym, currency=s["currency"], sector=s["sector"],
                  liquidity="liquid", valuation_method="market")
        listed[sym] = a
        days = all_days if sym == "BTC" else weekdays
        series[sym] = walk(rng, s["start"], days, s["drift"], s["vol"])
    northwind = asset(name="Northwind Robotics (SAFE)", asset_class="startup", currency="USD", liquidity="illiquid",
                      valuation_method="manual", sector="Robotics")
    lumen = asset(name="Lumen Health (Seed preferred)", asset_class="startup", currency="USD", liquidity="illiquid",
                  valuation_method="manual", sector="Healthtech")
    quill = asset(name="Quill Labs (SAFE)", asset_class="startup", currency="USD", liquidity="illiquid",
                  valuation_method="manual", sector="Developer tools")
    flat = asset(name="Riverside flat", asset_class="real_estate", currency="USD", liquidity="illiquid",
                 valuation_method="manual", country="US")
    db.flush()

    for sym, prices in series.items():
        for d, p in prices.items():
            db.add(Price(asset_id=listed[sym].id, date=d, price=p, currency=listed[sym].currency, source="demo"))
    eur = walk(rng, 1.08, weekdays, 0.0, 0.07)
    for d, r in eur.items():
        db.add(FxRate(currency="EUR", base="USD", date=d, rate=D(str(round(float(r), 4))), source="demo"))

    def px(sym: str, d: date) -> Decimal:
        s = series[sym]
        while d not in s:
            d -= timedelta(days=1)
            if d < start:
                return next(iter(s.values()))
        return s[d]

    def fx_on(d: date) -> Decimal:
        while d not in eur:
            d -= timedelta(days=1)
            if d < start:
                return next(iter(eur.values()))
        return D(str(round(float(eur[d]), 4)))

    def tx(account, typ, d, **kw):
        if d > today:  # monthly schedules can run past today; keep history in the past
            return
        db.add(Transaction(account_id=account.id, type=typ, trade_date=d, currency=kw.pop("currency", "USD"),
                           source="manual", **kw))

    # --- Interactive Brokers: initial portfolio, monthly savings, dividends ---------------
    tx(ibkr, "deposit", start, amount=D(100000))
    d1 = start + timedelta(days=1)
    for sym, qty in (("VTI", 150), ("AAPL", 60), ("MSFT", 40), ("BND", 250)):
        tx(ibkr, "buy", d1, asset_id=listed[sym].id, quantity=D(qty), price=px(sym, d1), fees=D(1))
    d_fx = start + timedelta(days=9)
    eur_bought = q2(D(20000) / fx_on(d_fx))
    tx(ibkr, "fx", d_fx, amount=D(20000), currency="USD", counter_amount=eur_bought, counter_currency="EUR",
       notes="EUR.USD")
    d_asml = start + timedelta(days=10)
    asml_qty = int((eur_bought - 5) / px("ASML", d_asml))
    tx(ibkr, "buy", d_asml, asset_id=listed["ASML"].id, quantity=D(asml_qty), price=px("ASML", d_asml),
       fees=D("1.25"), currency="EUR")

    month = date(start.year, start.month, 1)
    while True:
        month = date(month.year + (month.month // 12), month.month % 12 + 1, 1)
        d = month + timedelta(days=2)
        if d > today:
            break
        tx(ibkr, "deposit", d, amount=D(1500))
        shares = int(D(1500) / px("VTI", d))
        tx(ibkr, "buy", d, asset_id=listed["VTI"].id, quantity=D(shares), price=px("VTI", d), fees=D(1))
        tx(ibkr, "interest", d + timedelta(days=1), amount=q2(rng.uniform(4, 12)), notes="Credit interest")
        tx(ibkr, "dividend", d + timedelta(days=5), asset_id=listed["BND"].id, amount=q2(250 * 0.21))
        if month.month in (3, 6, 9, 12):
            tx(ibkr, "dividend", d + timedelta(days=20), asset_id=listed["VTI"].id, amount=q2(150 * 0.95))
            tx(ibkr, "dividend", d + timedelta(days=12), asset_id=listed["MSFT"].id, amount=q2(40 * 0.75))
        if month.month in (2, 5, 8, 11):
            tx(ibkr, "dividend", d + timedelta(days=10), asset_id=listed["AAPL"].id, amount=q2(60 * 0.25))
        if month.month == 5:
            div = q2(asml_qty * 1.52)
            tx(ibkr, "dividend", d + timedelta(days=8), asset_id=listed["ASML"].id, amount=div, currency="EUR")
            tx(ibkr, "tax", d + timedelta(days=8), asset_id=listed["ASML"].id, amount=q2(div * D("0.15")),
               currency="EUR", notes="NL dividend withholding")
        if month.month == 1:
            tx(ibkr, "fee", d, amount=D(120), notes="Market data subscription")

    d_sell = start + timedelta(days=420)
    tx(ibkr, "sell", d_sell, asset_id=listed["AAPL"].id, quantity=D(20), price=px("AAPL", d_sell), fees=D(1))

    # --- Crypto ---------------------------------------------------------------------------
    d_btc = start + timedelta(days=5)
    tx(wallet, "buy", d_btc, asset_id=listed["BTC"].id, quantity=D("0.8"), price=px("BTC", d_btc), fees=D(15))

    # --- Startups ---------------------------------------------------------------------------
    d = start + timedelta(days=30)
    tx(direct, "buy", d, asset_id=northwind.id, quantity=D(1), price=D(25000), notes="SAFE, $8M cap, 20% discount")
    db.add(Valuation(asset_id=northwind.id, date=d + timedelta(days=540), price=D(60000), currency="USD",
                     method="last_round", source="Series A at $19M pre", confidence="medium"))
    d = start + timedelta(days=75)
    tx(direct, "buy", d, asset_id=lumen.id, quantity=D(40000), price=D(1), notes="Seed preferred at $1.00/share")
    db.add(Valuation(asset_id=lumen.id, date=d + timedelta(days=400), price=D("1.80"), currency="USD",
                     method="last_round", source="Series A at $1.80/share", confidence="high"))
    db.add(Valuation(asset_id=lumen.id, date=today - timedelta(days=120), price=D("1.50"), currency="USD",
                     method="write_down", source="Q2 investor update: missed revenue plan", confidence="low"))
    d = start + timedelta(days=120)
    tx(direct, "buy", d, asset_id=quill.id, quantity=D(1), price=D(15000), notes="SAFE, $6M cap")
    tx(direct, "write_off", d + timedelta(days=600), asset_id=quill.id, notes="Company wound down")

    # --- Real estate (50% share) ---------------------------------------------------------------
    d_flat = start + timedelta(days=60)
    tx(flat_acct, "buy", d_flat, asset_id=flat.id, quantity=D(1), price=D(420000), fees=D(9000))
    for y in range(1, years + 1):
        db.add(Valuation(asset_id=flat.id, date=d_flat + timedelta(days=365 * y - 20),
                         price=q2(420000 * 1.04 ** y), currency="USD", method="appraisal",
                         source="Annual estimate", confidence="medium"))
        tx(flat_acct, "expense", d_flat + timedelta(days=365 * y - 30), asset_id=flat.id, amount=D(3200),
           notes="Insurance and maintenance")
    m = date(d_flat.year, d_flat.month, 1)
    while True:
        m = date(m.year + (m.month // 12), m.month % 12 + 1, 1)
        if m > today:
            break
        tx(flat_acct, "rent", m, asset_id=flat.id, amount=D(1850))

    db.commit()
    db.close()
    print("Demo portfolio created.")


if __name__ == "__main__":
    seed()
