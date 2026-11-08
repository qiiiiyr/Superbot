"""Approval queue: modules propose side effects; core runs them only after the owner approves."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, text

from superbot.core import db, pause

Executor = Callable[[dict], dict]
_executors: dict[str, Executor] = {}


class ApprovalError(Exception):
    pass


def executor(kind: str) -> Callable[[Executor], Executor]:
    def register(fn: Executor) -> Executor:
        _executors[kind] = fn
        return fn

    return register


def _now() -> str:
    # ISO strings in UTC sort correctly, so SQL can compare them directly
    return datetime.now(UTC).isoformat()


def _audit(
    c: Connection, action_id: int, event: str, actor: str, detail: str | None = None
) -> None:
    c.execute(
        text(
            "INSERT INTO audit_log (action_id, event, actor, detail, at)"
            " VALUES (:a, :e, :who, :d, :t)"
        ),
        {"a": action_id, "e": event, "who": actor, "d": detail, "t": _now()},
    )


def propose(kind: str, title: str, payload: dict) -> int:
    if kind not in _executors:
        raise ApprovalError(f"Unknown action kind {kind!r}: no executor registered")
    with db.engine().begin() as c:
        action_id = c.execute(
            text(
                "INSERT INTO actions (kind, title, payload, status, created_at)"
                " VALUES (:k, :ti, :p, 'pending', :t) RETURNING id"
            ),
            {"k": kind, "ti": title, "p": json.dumps(payload), "t": _now()},
        ).scalar_one()
        _audit(c, action_id, "proposed", kind.split(".")[0])
    return action_id


def _decide(action_id: int, status: str, actor: str) -> None:
    with db.engine().begin() as c:
        changed = c.execute(
            text("UPDATE actions SET status=:s, decided_at=:t WHERE id=:i AND status='pending'"),
            {"s": status, "t": _now(), "i": action_id},
        ).rowcount
        if changed != 1:
            raise ApprovalError(f"Action {action_id} is not pending")
        _audit(c, action_id, status, actor)


def approve(action_id: int, actor: str = "owner") -> None:
    _decide(action_id, "approved", actor)


def reject(action_id: int, actor: str = "owner") -> None:
    _decide(action_id, "rejected", actor)


def _row(r) -> dict:
    d = dict(r._mapping)
    for key in ("payload", "result"):
        if d.get(key) is not None:
            d[key] = json.loads(d[key])
    return d


def get(action_id: int) -> dict | None:
    with db.engine().connect() as c:
        r = c.execute(text("SELECT * FROM actions WHERE id=:i"), {"i": action_id}).first()
    return _row(r) if r else None


def list_pending() -> list[dict]:
    with db.engine().connect() as c:
        rows = c.execute(text("SELECT * FROM actions WHERE status='pending' ORDER BY id"))
        return [_row(r) for r in rows]


def list_recent(limit: int = 50) -> list[dict]:
    """Everything already decided or finished, newest first."""
    with db.engine().connect() as c:
        rows = c.execute(
            text("SELECT * FROM actions WHERE status != 'pending' ORDER BY id DESC LIMIT :n"),
            {"n": limit},
        )
        return [_row(r) for r in rows]


def expire_old(hours: int) -> int:
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    expired = 0
    with db.engine().begin() as c:
        ids = c.execute(
            text("SELECT id FROM actions WHERE status='pending' AND created_at < :c"), {"c": cutoff}
        ).scalars()
        for action_id in list(ids):
            if c.execute(
                text(
                    "UPDATE actions SET status='expired', decided_at=:t"
                    " WHERE id=:i AND status='pending'"
                ),
                {"t": _now(), "i": action_id},
            ).rowcount:
                _audit(c, action_id, "expired", "system")
                expired += 1
    return expired


def _finish(action_id: int, status: str, result: dict | None, error: str | None) -> None:
    with db.engine().begin() as c:
        c.execute(
            text(
                "UPDATE actions SET status=:s, executed_at=:t, result=:r, error=:e"
                " WHERE id=:i AND status='executing'"
            ),
            {
                "s": status,
                "t": _now(),
                "r": None if result is None else json.dumps(result, default=str),
                "e": error,
                "i": action_id,
            },
        )
        _audit(c, action_id, status, "system", error)


def run_approved() -> int:
    """Run every approved action at most once. Returns how many this call ran."""
    with db.engine().connect() as c:
        rows = c.execute(
            text("SELECT id, kind, payload FROM actions WHERE status='approved' ORDER BY id")
        ).all()
    ran = 0
    for action_id, kind, payload in rows:
        if pause.is_paused():
            break
        # The claim is the only double-run guard: one atomic UPDATE, no prior read in this txn.
        with db.engine().begin() as c:
            if (
                c.execute(
                    text("UPDATE actions SET status='executing' WHERE id=:i AND status='approved'"),
                    {"i": action_id},
                ).rowcount
                != 1
            ):
                continue
            _audit(c, action_id, "executing", "system")
        ran += 1
        fn = _executors.get(kind)
        if fn is None:
            _finish(action_id, "failed", None, f"No executor registered for {kind!r}")
            continue
        try:
            result = fn(json.loads(payload))
        except Exception as e:  # never retried: money actions must be checked by a human
            _finish(action_id, "failed", None, f"{type(e).__name__}: {e}")
        else:
            _finish(action_id, "executed", result, None)
    return ran


def recover_interrupted() -> int:
    """At startup, anything still 'executing' was cut off mid-run; we can't know if it happened."""
    with db.engine().begin() as c:
        ids = c.execute(text("SELECT id FROM actions WHERE status='executing'")).scalars().all()
    for action_id in ids:
        _finish(action_id, "failed", None, "interrupted — check manually")
    return len(ids)
