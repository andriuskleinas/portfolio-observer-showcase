"""Replays transactions day by day into per-component values, flows and events.

A component is either a holding ("h", account_id, asset_id) or a cash balance
("c", account_id, currency). Every transaction books flows on the components it
touches, seen from the component: positive = money in, negative = money out.
When both sides of a movement are in a selection (a buy paid from the same
account's cash) the flows cancel, so only money crossing the selection's
boundary counts as an external flow. Accounts that don't track cash (direct
startup deals, property) have no cash component, so their buys and income are
external flows by construction.

All values, flows and events are in the base currency and scaled by the
account's ownership share.
"""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property
from decimal import Decimal

from app.engine.market import FxBook, PriceBook
from app.engine.types import ONE, ZERO, AccountInfo, AssetInfo, Observation, Tx
from app.taxonomy import INCOME_TYPES

# Same-day processing order: money arrives before it is spent, sales before withdrawals.
_ORDER = {"deposit": 0, "transfer_in": 1, "fx": 2, "split": 3, "capital_call": 4, "buy": 5,
          "sell": 8, "transfer_out": 9, "withdrawal": 10}


@dataclass
class Lot:
    date: date
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal


@dataclass
class HoldingState:
    account_id: int
    asset_id: int
    quantity: Decimal = ZERO
    lots: list[Lot] = field(default_factory=list)
    first_date: date | None = None

    @property
    def cost_base(self) -> Decimal:
        return sum((lot.cost_base for lot in self.lots), ZERO)

    @property
    def cost_local(self) -> Decimal:
        return sum((lot.cost_local for lot in self.lots), ZERO)


@dataclass(frozen=True)
class Event:
    date: date
    key: tuple
    kind: str  # income | realized | fee | tax
    amount: Decimal  # base currency, ownership-scaled


@dataclass
class History:
    base: str
    dates: list[date]
    values: dict[tuple, list[Decimal]]
    flows: dict[tuple, dict[date, Decimal]]
    events: list[Event]
    holdings: dict[tuple, HoldingState]
    cash: dict[tuple, Decimal]
    accounts: dict[int, AccountInfo]
    assets: dict[int, AssetInfo]
    prices: PriceBook
    fx: FxBook
    warnings: list[str]

    def index(self, d: date) -> int:
        """Index of the last date on or before d (-1 if before the first date)."""
        return bisect_right(self.dates, d) - 1

    @cached_property
    def events_by_key(self) -> dict[tuple, list[Event]]:
        out: dict[tuple, list[Event]] = defaultdict(list)
        for e in self.events:
            out[e.key].append(e)
        return dict(out)

    @property
    def start(self) -> date | None:
        return self.dates[0] if self.dates else None

    @property
    def end(self) -> date | None:
        return self.dates[-1] if self.dates else None


class _Replay:
    def __init__(self, accounts, assets, prices: PriceBook, fx: FxBook, dates: list[date]):
        self.accounts = accounts
        self.assets = assets
        self.prices = prices
        self.fx = fx
        self.dates = dates
        self.n = len(dates)
        self.values: dict[tuple, list[Decimal]] = {}
        self.flows: dict[tuple, dict[date, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
        self.events: list[Event] = []
        self.holdings: dict[tuple, HoldingState] = {}
        self.cash: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        self.last_tx_fx: dict[str, Decimal] = {}
        self.warnings: dict[str, None] = {}

    # --- helpers -----------------------------------------------------------------

    def warn(self, msg: str) -> None:
        self.warnings[msg] = None

    def _touch(self, key: tuple) -> None:
        if key not in self.values:
            self.values[key] = [ZERO] * self.n

    def rate(self, currency: str, d: date, t: Tx | None = None) -> Decimal:
        if t is not None and t.fx_rate_to_base and currency == t.currency:
            self.last_tx_fx[currency] = t.fx_rate_to_base
            return t.fx_rate_to_base
        r = self.fx.rate(currency, d)
        if r is None:
            r = self.last_tx_fx.get(currency)
        if r is None:
            self.warn(f"Missing FX rate for {currency}; using 1.0 — refresh FX rates")
            return ONE
        return r

    def holding(self, key: tuple, d: date) -> HoldingState:
        hs = self.holdings.get(key)
        if hs is None:
            hs = self.holdings[key] = HoldingState(account_id=key[1], asset_id=key[2], first_date=d)
            self._touch(key)
        return hs

    def flow(self, key: tuple, d: date, amount: Decimal, own: Decimal) -> None:
        self._touch(key)
        self.flows[key][d] += amount * own

    def event(self, key: tuple, d: date, kind: str, amount: Decimal, own: Decimal) -> None:
        self._touch(key)
        self.events.append(Event(d, key, kind, amount * own))

    def cash_add(self, key: tuple, amount: Decimal) -> None:
        self._touch(key)
        self.cash[key] += amount

    def consume(self, hs: HoldingState, qty: Decimal) -> tuple[Decimal, Decimal]:
        """Remove qty from the holding's lots FIFO (D6). Returns removed (cost_local, cost_base)."""
        remaining, cost_l, cost_b = qty, ZERO, ZERO
        while remaining > 0 and hs.lots:
            lot = hs.lots[0]
            take = min(lot.quantity, remaining)
            frac = take / lot.quantity if lot.quantity else ONE
            cl, cb = lot.cost_local * frac, lot.cost_base * frac
            lot.quantity -= take
            lot.cost_local -= cl
            lot.cost_base -= cb
            cost_l += cl
            cost_b += cb
            remaining -= take
            if lot.quantity <= 0:
                hs.lots.pop(0)
        if remaining > 0:
            name = self.assets[hs.asset_id].name if hs.asset_id in self.assets else hs.asset_id
            self.warn(f"Sold or transferred more {name} than held — check for missing transactions")
        return cost_l, cost_b

    # --- transactions --------------------------------------------------------------

    def apply(self, t: Tx) -> None:
        acct = self.accounts[t.account_id]
        own, d = acct.ownership, t.date
        q = t.quantity if t.quantity is not None else ZERO
        amt = t.amount if t.amount is not None else ZERO
        fees = t.fees or ZERO
        hk = ("h", acct.id, t.asset_id) if t.asset_id is not None else None
        ck = ("c", acct.id, t.currency)
        tracks_cash = acct.tracks_cash
        typ = t.type

        if hk is None and typ in {"buy", "sell", "coupon", "rent", "distribution", "staking_reward", "capital_call",
                                  "return_of_capital", "transfer_in", "transfer_out", "split", "airdrop", "write_off"}:
            self.warn(f"Transaction {t.id} ({typ}) has no asset and was skipped")
            return

        if typ in ("buy", "capital_call"):
            gross = q * t.price if (t.price is not None and q) else amt
            total = gross + fees
            tb = total * self.rate(t.currency, d, t)
            hs = self.holding(hk, d)
            if q:
                hs.lots.append(Lot(d, q, total, tb))
                hs.quantity += q
            elif hs.lots:  # capital call on an existing fund position adds cost, not units
                hs.lots[-1].cost_local += total
                hs.lots[-1].cost_base += tb
            else:
                hs.lots.append(Lot(d, ONE, total, tb))
                hs.quantity = ONE
            self.flow(hk, d, tb, own)
            if tracks_cash:
                self.cash_add(ck, -total)
                self.flow(ck, d, -tb, own)

        elif typ == "sell":
            proceeds = q * (t.price or ZERO) - fees
            pb = proceeds * self.rate(t.currency, d, t)
            hs = self.holding(hk, d)
            _, cost_b = self.consume(hs, q)
            hs.quantity -= q
            self.event(hk, d, "realized", pb - cost_b, own)
            self.flow(hk, d, -pb, own)
            if tracks_cash:
                self.cash_add(ck, proceeds)
                self.flow(ck, d, pb, own)

        elif typ in INCOME_TYPES and typ != "staking_reward":
            ab = amt * self.rate(t.currency, d, t)
            if hk:
                self.holding(hk, d)
                self.event(hk, d, "income", ab, own)
                self.flow(hk, d, -ab, own)
                if tracks_cash:
                    self.cash_add(ck, amt)
                    self.flow(ck, d, ab, own)
            elif tracks_cash:  # e.g. interest on cash: a return on the cash balance itself
                self.event(ck, d, "income", ab, own)
                self.cash_add(ck, amt)
            else:
                self.warn(f"{typ.capitalize()} without an asset in '{acct.name}' (no cash tracking) was skipped")

        elif typ == "staking_reward":
            value_l = q * (t.price or ZERO)
            vb = value_l * self.rate(self.assets[t.asset_id].currency, d)
            hs = self.holding(hk, d)
            hs.lots.append(Lot(d, q, value_l, vb))
            hs.quantity += q
            self.event(hk, d, "income", vb, own)

        elif typ == "airdrop":
            hs = self.holding(hk, d)
            hs.lots.append(Lot(d, q, ZERO, ZERO))
            hs.quantity += q

        elif typ in ("fee", "tax", "expense"):
            ab = amt * self.rate(t.currency, d, t)
            kind = "tax" if typ == "tax" else "fee"
            if hk:
                self.holding(hk, d)
                self.event(hk, d, kind, ab, own)
                self.flow(hk, d, ab, own)  # money put into the holding without adding value
                if tracks_cash:
                    self.cash_add(ck, -amt)
                    self.flow(ck, d, -ab, own)
            elif tracks_cash:
                self.event(ck, d, kind, ab, own)
                self.cash_add(ck, -amt)
            else:
                self.warn(f"{typ.capitalize()} without an asset in '{acct.name}' (no cash tracking) was skipped")

        elif typ in ("transfer_in", "transfer_out"):
            asset = self.assets[t.asset_id]
            price = t.price
            if price is None:
                obs = self.prices.latest(t.asset_id, d)
                price = obs.price if obs else ZERO
            value_l = q * price
            vb = value_l * self.rate(asset.currency, d)
            hs = self.holding(hk, d)
            if typ == "transfer_in":
                hs.lots.append(Lot(d, q, value_l, vb))
                hs.quantity += q
                self.flow(hk, d, vb, own)
            else:
                self.consume(hs, q)
                hs.quantity -= q
                self.flow(hk, d, -vb, own)

        elif typ == "fx":
            if not t.counter_currency or t.counter_amount is None:
                self.warn(f"Currency exchange {t.id} is missing the bought currency or amount")
                return
            if not tracks_cash:
                self.warn(f"Currency exchange in '{acct.name}' ignored: account doesn't track cash")
                return
            b = amt * self.rate(t.currency, d, t)
            c2 = ("c", acct.id, t.counter_currency)
            self.cash_add(ck, -amt)
            self.cash_add(c2, t.counter_amount)
            # Both legs carry the sold leg's base value so they cancel exactly; the
            # conversion spread then shows up as a change in value, i.e. as return.
            self.flow(ck, d, -b, own)
            self.flow(c2, d, b, own)

        elif typ in ("deposit", "withdrawal"):
            if not tracks_cash:
                self.warn(f"{typ.capitalize()} in '{acct.name}' ignored: account doesn't track cash")
                return
            sign = ONE if typ == "deposit" else -ONE
            ab = amt * self.rate(t.currency, d, t)
            self.cash_add(ck, sign * amt)
            self.flow(ck, d, sign * ab, own)

        elif typ == "split":
            if q <= 0:
                self.warn(f"Split {t.id} needs a positive ratio in quantity")
                return
            hs = self.holding(hk, d)
            hs.quantity *= q
            for lot in hs.lots:
                lot.quantity *= q

        elif typ == "write_off":
            hs = self.holding(hk, d)
            self.event(hk, d, "realized", -hs.cost_base, own)
            hs.lots.clear()
            hs.quantity = ZERO

        elif typ == "return_of_capital":
            ab = amt * self.rate(t.currency, d, t)
            hs = self.holding(hk, d)
            cost_b, cost_l = hs.cost_base, hs.cost_local
            if cost_b > 0:
                factor = max(ZERO, ONE - ab / cost_b)
                for lot in hs.lots:
                    lot.cost_base *= factor
                    lot.cost_local *= factor
            if ab > cost_b:
                self.event(hk, d, "realized", ab - max(cost_b, ZERO), own)
            self.flow(hk, d, -ab, own)
            if tracks_cash:
                self.cash_add(ck, amt)
                self.flow(ck, d, ab, own)
        else:
            self.warn(f"Unknown transaction type '{typ}' ({t.id}) was skipped")

    # --- daily valuation -------------------------------------------------------------

    def value_day(self, i: int, d: date) -> None:
        for key, hs in self.holdings.items():
            if hs.quantity == 0:
                continue
            asset = self.assets[hs.asset_id]
            obs = self.prices.latest(hs.asset_id, d)
            if obs is None:
                self.warn(f"No price or valuation for {asset.name}; valued at 0")
                continue
            own = self.accounts[hs.account_id].ownership
            self.values[key][i] = hs.quantity * obs.price * self.rate(asset.currency, d) * own
        for key, bal in self.cash.items():
            if bal == 0:
                continue
            own = self.accounts[key[1]].ownership
            self.values[key][i] = bal * self.rate(key[2], d) * own


def build_history(txs: list[Tx], accounts: dict[int, AccountInfo], assets: dict[int, AssetInfo],
                  prices: PriceBook, fx: FxBook, end: date) -> History:
    ordered = sorted((t for t in txs if t.date <= end), key=lambda t: (t.date, _ORDER.get(t.type, 6), t.id))
    first = ordered[0].date if ordered else end
    dates = [first + timedelta(days=i) for i in range((end - first).days + 1)]

    by_day: dict[date, list[Tx]] = defaultdict(list)
    for t in ordered:
        by_day[t.date].append(t)

    r = _Replay(accounts, assets, prices, fx, dates)
    for i, d in enumerate(dates):
        for t in by_day.get(d, ()):
            r.apply(t)
        r.value_day(i, d)

    return History(
        base=fx.base, dates=dates, values=r.values,
        flows={k: dict(v) for k, v in r.flows.items()}, events=r.events,
        holdings=r.holdings, cash=dict(r.cash), accounts=accounts, assets=assets,
        prices=prices, fx=fx, warnings=list(r.warnings),
    )


def trade_observations(txs: list[Tx]) -> list[tuple[int, Observation]]:
    """Trade prices double as the fallback price when nothing better exists."""
    out = []
    for t in txs:
        if t.asset_id is not None and t.price is not None and t.type in ("buy", "sell", "transfer_in", "transfer_out"):
            out.append((t.asset_id, Observation(t.date, t.price, "trade")))
    return out


def quantities(txs: list[Tx]) -> dict[tuple[int, int], Decimal]:
    """Quantity per (account, asset) after all transactions — used for import reconciliation."""
    qty: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for t in sorted(txs, key=lambda t: (t.date, _ORDER.get(t.type, 6), t.id)):
        if t.asset_id is None:
            continue
        k = (t.account_id, t.asset_id)
        q = t.quantity or ZERO
        if t.type in ("buy", "transfer_in", "staking_reward", "airdrop") or (t.type == "capital_call" and q):
            qty[k] += q
        elif t.type in ("sell", "transfer_out"):
            qty[k] -= q
        elif t.type == "split" and q > 0:
            qty[k] *= q
        elif t.type == "write_off":
            qty[k] = ZERO
    return dict(qty)
