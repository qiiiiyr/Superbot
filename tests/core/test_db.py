from sqlalchemy import inspect, text

from superbot.core.db import make_engine, migrate

TABLES = {"actions", "audit_log", "llm_usage", "settings_kv"}


def test_migrate_creates_tables_and_is_idempotent(db_url):
    migrate(db_url)
    migrate(db_url)  # second run is a no-op
    names = set(inspect(make_engine(db_url)).get_table_names())
    assert TABLES <= names


def test_engine_uses_wal(db_url):
    migrate(db_url)
    with make_engine(db_url).connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert c.execute(text("PRAGMA busy_timeout")).scalar() == 5000
