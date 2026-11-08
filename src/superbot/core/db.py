from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url

DEFAULT_URL = "sqlite:///data/superbot.db"
MIGRATIONS = Path(__file__).parent.parent / "migrations"


def make_engine(url: str = DEFAULT_URL) -> Engine:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


def migrate(url: str = DEFAULT_URL) -> None:
    db = make_url(url).database
    if db and db != ":memory:":
        Path(db).parent.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


_engine: Engine | None = None


def use(url: str = DEFAULT_URL) -> Engine:
    """Point the shared engine at `url` (tests use a temp DB)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = make_engine(url)
    return _engine


def engine() -> Engine:
    return _engine or use()
