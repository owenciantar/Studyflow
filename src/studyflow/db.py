"""SQLite persistence: schema, migrations, and all queries."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

from platformdirs import user_data_dir

_DB_PATH: Path | None = None


def db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        base = Path(user_data_dir("studyflow", appauthor=False))
        base.mkdir(parents=True, exist_ok=True)
        _DB_PATH = base / "studyflow.db"
    return _DB_PATH


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    ended_at         TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    tag              TEXT,
    xp_awarded       INTEGER NOT NULL DEFAULT 0,
    abandoned        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unlocks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    unlocked_at  TEXT NOT NULL,
    UNIQUE(kind, name)
);
"""

_DEFAULTS: dict[str, str] = {
    "daily_goal_minutes": "120",
    "total_xp": "0",
}


def init_db() -> None:
    """Create tables and seed state defaults."""
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        for key, val in _DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO state (key, value) VALUES (?, ?)", (key, val)
            )


def get_state(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_state(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, value)
        )


def save_session_and_xp(
    started_at: datetime,
    ended_at: datetime,
    duration_seconds: int,
    tag: str | None,
    xp_earned: int,
    new_total_xp: int,
) -> int:
    """Atomically record a session and update total XP. Returns new session id."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (started_at, ended_at, duration_seconds, tag, xp_awarded, abandoned)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (
                started_at.isoformat(),
                ended_at.isoformat(),
                duration_seconds,
                tag,
                xp_earned,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES ('total_xp', ?)",
            (str(new_total_xp),),
        )
        return int(cur.lastrowid)  # type: ignore[arg-type]


def record_abandoned(
    started_at: datetime,
    ended_at: datetime,
    duration_seconds: int,
    tag: str | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO sessions
               (started_at, ended_at, duration_seconds, tag, xp_awarded, abandoned)
               VALUES (?, ?, ?, ?, 0, 1)""",
            (started_at.isoformat(), ended_at.isoformat(), duration_seconds, tag),
        )


def get_sessions(days: int = 365) -> list[sqlite3.Row]:
    """Non-abandoned sessions within the last N days, newest first."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        return conn.execute(  # type: ignore[return-value]
            """SELECT * FROM sessions
               WHERE abandoned = 0 AND started_at >= ?
               ORDER BY started_at DESC""",
            (since,),
        ).fetchall()


def get_lifetime_hours() -> float:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) AS t FROM sessions WHERE abandoned = 0"
        ).fetchone()
        return float(row["t"]) / 3600.0


def get_daily_totals(days: int = 14) -> dict[date, int]:
    """Map local date → total seconds studied (non-abandoned sessions)."""
    rows = get_sessions(days=days + 1)
    totals: dict[date, int] = {}
    for row in rows:
        d = datetime.fromisoformat(row["started_at"]).astimezone().date()
        totals[d] = totals.get(d, 0) + row["duration_seconds"]
    return totals


def get_today_seconds() -> int:
    return get_daily_totals(days=1).get(date.today(), 0)


def add_unlock(kind: str, name: str) -> bool:
    """Insert unlock; returns True if newly added."""
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO unlocks (kind, name, unlocked_at) VALUES (?, ?, ?)",
                (kind, name, now),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_unlocks() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM unlocks ORDER BY unlocked_at").fetchall()  # type: ignore[return-value]
