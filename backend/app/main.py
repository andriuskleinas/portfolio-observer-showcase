import logging
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import dashboard, imports, records, system
from app.config import ROOT, settings
from app.db import SessionLocal, engine
from app.providers import fx_frankfurter
from app.services.portfolio import ensure_portfolio

log = logging.getLogger("portfolio")
BACKEND = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT / "frontend" / "dist"


def run_migrations() -> None:
    """Upgrade the schema on start; back up the database first when a migration is pending (DATA-05)."""
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current == head:
        return
    db_file = Path(engine.url.database) if engine.url.database else None
    if current is not None and db_file and db_file.exists():
        settings.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(db_file, settings.backups_dir / f"pre-migration-{stamp}.db")
    command.upgrade(cfg, "head")


def _refresh_fx() -> None:
    db = SessionLocal()
    try:
        result = fx_frankfurter.refresh(db)
        if result["errors"]:
            log.warning("FX refresh errors: %s", result["errors"])
    except Exception:  # network trouble must never stop the app (graceful degradation)
        log.exception("FX refresh failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    with SessionLocal() as db:
        ensure_portfolio(db)
    threading.Thread(target=_refresh_fx, daemon=True).start()
    yield


app = FastAPI(title="Portfolio Observer", lifespan=lifespan)
for r in (records.router, dashboard.router, imports.router, system.router):
    app.include_router(r)

if FRONTEND_DIST.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIST / "static", check_dir=False), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
