from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class AccountInfo:
    id: int
    name: str
    currency: str = "USD"
    tracks_cash: bool = True
    ownership: Decimal = ONE


@dataclass(frozen=True)
class AssetInfo:
    id: int
    name: str
    asset_class: str
    currency: str = "USD"
    symbol: str | None = None
    liquidity: str = "liquid"
    valuation_method: str = "market"


@dataclass(frozen=True)
class Tx:
    id: int
    account_id: int
    type: str
    date: date
    asset_id: int | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal | None = None
    currency: str = "USD"
    counter_amount: Decimal | None = None
    counter_currency: str | None = None
    fees: Decimal = ZERO
    fx_rate_to_base: Decimal | None = None


@dataclass(frozen=True)
class Observation:
    """A price point for one unit of an asset, in the asset's currency."""

    date: date
    price: Decimal
    source: str  # "trade" | "market" | "mark"
