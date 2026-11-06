from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.taxonomy import ACCOUNT_TYPES, ASSET_CLASSES, TX_TYPES, VALUATION_METHODS


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    institution: str | None = None
    type: str = "broker"
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tracks_cash: bool | None = None
    ownership_pct: Decimal = Field(default=Decimal(1), gt=0, le=1)
    external_ref: str | None = None
    notes: str | None = None
    archived: bool = False

    @model_validator(mode="after")
    def _check(self):
        if self.type not in ACCOUNT_TYPES:
            raise ValueError(f"Unknown account type '{self.type}'")
        if self.tracks_cash is None:
            self.tracks_cash = ACCOUNT_TYPES[self.type]["tracks_cash"]
        self.currency = self.currency.upper()
        return self


class AccountOut(AccountIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    asset_class: str
    sub_class: str | None = None
    symbol: str | None = None
    isin: str | None = Field(default=None, max_length=12)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    country: str | None = None
    sector: str | None = None
    liquidity: str | None = None
    valuation_method: str | None = None
    tags: list[str] = []
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.asset_class not in ASSET_CLASSES or self.asset_class == "cash":
            raise ValueError(f"Unknown asset class '{self.asset_class}'")
        meta = ASSET_CLASSES[self.asset_class]
        self.liquidity = self.liquidity or meta["liquidity"]
        self.valuation_method = self.valuation_method or meta["valuation"]
        self.currency = self.currency.upper()
        return self


class AssetOut(AssetIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_ids: dict = {}


class TransactionIn(BaseModel):
    account_id: int
    asset_id: int | None = None
    type: str
    trade_date: date
    quantity: Decimal | None = None
    price: Decimal | None = Field(default=None, ge=0)
    amount: Decimal | None = None
    currency: str | None = None
    counter_amount: Decimal | None = None
    counter_currency: str | None = None
    fees: Decimal = Field(default=Decimal(0), ge=0)
    fx_rate_to_base: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self):
        meta = TX_TYPES.get(self.type)
        if meta is None:
            raise ValueError(f"Unknown transaction type '{self.type}'")
        if meta["asset"] == "required" and self.asset_id is None:
            raise ValueError(f"{meta['label']} needs an asset")
        if meta["asset"] == "none":
            self.asset_id = None
        if self.type in ("buy", "sell", "transfer_in", "staking_reward", "airdrop", "split") and not (self.quantity and self.quantity > 0):
            raise ValueError(f"{meta['label']} needs a positive quantity")
        if self.type in ("buy", "sell") and self.price is None:
            raise ValueError(f"{meta['label']} needs a price")
        if "amount" in meta["fields"] and self.type != "capital_call" and self.amount is None:
            raise ValueError(f"{meta['label']} needs an amount")
        if self.type == "capital_call" and self.amount is None and not (self.quantity and self.price is not None):
            raise ValueError("Capital call needs an amount")
        if self.type == "fx" and (not self.counter_currency or self.counter_amount is None):
            raise ValueError("Currency exchange needs the bought currency and amount")
        if self.currency:
            self.currency = self.currency.upper()
        if self.counter_currency:
            self.counter_currency = self.counter_currency.upper()
        return self


class TransactionOut(TransactionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    currency: str
    source: str
    external_id: str | None = None
    import_batch_id: int | None = None
    asset_name: str | None = None
    asset_symbol: str | None = None
    account_name: str | None = None


class ValuationIn(BaseModel):
    asset_id: int
    date: date
    price: Decimal = Field(ge=0)
    currency: str | None = None
    method: str = "own_estimate"
    source: str | None = None
    confidence: str = "medium"
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.method not in VALUATION_METHODS:
            raise ValueError(f"Unknown valuation method '{self.method}'")
        if self.confidence not in ("low", "medium", "high"):
            raise ValueError("Confidence is low, medium or high")
        return self


class ValuationOut(ValuationIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    currency: str


class PriceIn(BaseModel):
    asset_id: int
    date: date
    price: Decimal = Field(ge=0)
    currency: str | None = None


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mapping: dict
