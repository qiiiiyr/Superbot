"""One switch that stops all jobs and all approved actions."""

from sqlalchemy import text

from superbot.core import db

_forced = False


def force(on: bool) -> None:
    """PAUSED=true in .env; main sets this at startup and the DB flag can't override it."""
    global _forced
    _forced = on


def is_forced() -> bool:
    return _forced


def set_paused(on: bool) -> None:
    with db.engine().begin() as c:
        c.execute(
            text(
                "INSERT INTO settings_kv (key, value) VALUES ('paused', :v)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            ),
            {"v": "1" if on else "0"},
        )


def is_paused() -> bool:
    if _forced:
        return True
    with db.engine().connect() as c:
        return c.execute(text("SELECT value FROM settings_kv WHERE key='paused'")).scalar() == "1"
