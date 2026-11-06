from decimal import Decimal

from sqlalchemy import String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import settings


class Base(DeclarativeBase):
    pass


class DecimalText(TypeDecorator):
    """Stores Decimal as TEXT so SQLite never rounds money through floats (DATA-01)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            value = str(value)
        return format(Decimal(value).normalize(), "f")

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return eng


engine = make_engine(settings.db_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Bumped on every flush that writes data; analytics caches key on it.
data_version = {"value": 0}


@event.listens_for(Session, "after_flush")
def _bump_version(session, _ctx):
    if session.new or session.dirty or session.deleted:
        data_version["value"] += 1


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
