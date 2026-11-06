"""Database models. Every owned record carries owner_id from day one (FUT-01)."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, DecimalText

OWNER_ID = 1  # single-user for now


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    name: Mapped[str] = mapped_column(String(200))
    institution: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30), default="broker")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    tracks_cash: Mapped[bool] = mapped_column(Boolean, default=True)
    ownership_pct: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal(1))
    external_ref: Mapped[str | None] = mapped_column(String(100))  # e.g. IBKR account id
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    name: Mapped[str] = mapped_column(String(300))
    asset_class: Mapped[str] = mapped_column(String(30), index=True)
    sub_class: Mapped[str | None] = mapped_column(String(60))
    symbol: Mapped[str | None] = mapped_column(String(40), index=True)
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    external_ids: Mapped[dict] = mapped_column(JSON, default=dict)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    country: Mapped[str | None] = mapped_column(String(60))
    sector: Mapped[str | None] = mapped_column(String(100))
    liquidity: Mapped[str] = mapped_column(String(10), default="liquid")
    valuation_method: Mapped[str] = mapped_column(String(10), default="market")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    kind: Mapped[str] = mapped_column(String(30))  # ibkr_flex | csv
    filename: Mapped[str | None] = mapped_column(String(300))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    status: Mapped[str] = mapped_column(String(20), default="preview")  # preview | committed | rolled_back
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # parsed rows + extras for preview
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportTemplate(Base):
    """Saved CSV column mappings per institution (DASH-03)."""

    __tablename__ = "import_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("account_id", "external_id", name="uq_tx_account_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[Decimal | None] = mapped_column(DecimalText)
    price: Mapped[Decimal | None] = mapped_column(DecimalText)
    amount: Mapped[Decimal | None] = mapped_column(DecimalText)
    currency: Mapped[str] = mapped_column(String(3))
    counter_amount: Mapped[Decimal | None] = mapped_column(DecimalText)
    counter_currency: Mapped[str | None] = mapped_column(String(3))
    fees: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal(0))
    fx_rate_to_base: Mapped[Decimal | None] = mapped_column(DecimalText)
    external_id: Mapped[str | None] = mapped_column(String(120))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    asset: Mapped[Asset | None] = relationship(lazy="joined")
    account: Mapped[Account] = relationship(lazy="joined")


class Price(Base):
    """Market prices, in the asset's currency."""

    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("asset_id", "date", "source", name="uq_price_asset_date_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[Decimal] = mapped_column(DecimalText)
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(40), default="manual")
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))


class Valuation(Base):
    """Manual or statement-based mark for assets without a market price (VAL-03). Price is per unit."""

    __tablename__ = "valuations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[Decimal] = mapped_column(DecimalText)
    currency: Mapped[str] = mapped_column(String(3))
    method: Mapped[str] = mapped_column(String(30), default="own_estimate")
    source: Mapped[str | None] = mapped_column(String(300))
    confidence: Mapped[str] = mapped_column(String(10), default="medium")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FxRate(Base):
    """1 unit of `currency` = `rate` units of `base` on `date`."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("currency", "base", "date", name="uq_fx_currency_base_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    base: Mapped[str] = mapped_column(String(3))
    date: Mapped[date] = mapped_column(Date, index=True)
    rate: Mapped[Decimal] = mapped_column(DecimalText)
    source: Mapped[str] = mapped_column(String(40))


class Attachment(Base):
    """Documents such as SAFEs, term sheets and statements (DASH-10)."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, default=OWNER_ID, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(100), unique=True)
    content_type: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
