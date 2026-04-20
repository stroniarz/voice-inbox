import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta


class DedupStore:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                announced_at TEXT NOT NULL,
                PRIMARY KEY (source, external_id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cursor (
                source TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                author TEXT NOT NULL,
                short TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                digested_at TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_digested ON events(digested_at)"
        )
        # Migration: add project column if missing
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(events)").fetchall()}
        if "project" not in cols:
            self.conn.execute("ALTER TABLE events ADD COLUMN project TEXT")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_project ON events(project)")
        self.conn.commit()

    def is_seen(self, source: str, external_id: str) -> bool:
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM seen WHERE source=? AND external_id=?",
                (source, external_id),
            ).fetchone()
        return row is not None

    def mark_seen(self, source: str, external_id: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO seen (source, external_id, announced_at) VALUES (?, ?, ?)",
                (source, external_id, datetime.now(timezone.utc).isoformat()),
            )
            self.conn.commit()

    def get_cursor(self, source: str) -> str | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT value FROM cursor WHERE source=?", (source,)
            ).fetchone()
        return row[0] if row else None

    def set_cursor(self, source: str, value: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO cursor (source, value) VALUES (?, ?) "
                "ON CONFLICT(source) DO UPDATE SET value=excluded.value",
                (source, value),
            )
            self.conn.commit()

    def archive_event(self, source: str, external_id: str, author: str,
                      short: str, title: str, body: str,
                      project: str | None = None) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO events (source, external_id, author, short, title, body, created_at, project) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source, external_id, author, short, title, body,
                 datetime.now(timezone.utc).isoformat(), project),
            )
            self.conn.commit()

    def recent_events(self, hours: int = 24,
                      project: str | None = None,
                      limit: int = 200) -> list[dict]:
        """Recent events for /status and /ask context. Most recent first."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        params: list = [cutoff]
        sql = (
            "SELECT id, source, project, author, short, title, body, created_at, digested_at "
            "FROM events WHERE created_at >= ?"
        )
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [
            {"id": r[0], "source": r[1], "project": r[2], "author": r[3],
             "short": r[4], "title": r[5], "body": r[6],
             "created_at": r[7], "digested_at": r[8]}
            for r in rows
        ]

    def project_summary(self, hours: int = 24,
                        project: str | None = None) -> list[dict]:
        """Aggregated per-project activity for /status endpoint and /ask context."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        sql = (
            "SELECT COALESCE(project, '(none)') AS p, source, "
            "COUNT(*) AS cnt, MAX(created_at) AS last_at "
            "FROM events WHERE created_at >= ?"
        )
        params: list = [cutoff]
        if project is not None:
            sql += " AND project = ?"
            params.append(project)
        sql += " GROUP BY p, source ORDER BY last_at DESC"
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [
            {"project": r[0], "source": r[1], "count": r[2], "last_at": r[3]}
            for r in rows
        ]

    def fetch_undigested(self, since_minutes: int = 60) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, source, author, short, title, body, created_at, project "
                "FROM events WHERE digested_at IS NULL AND created_at >= ? "
                "ORDER BY created_at ASC",
                (cutoff,),
            ).fetchall()
        return [
            {"id": r[0], "source": r[1], "author": r[2], "short": r[3],
             "title": r[4], "body": r[5], "created_at": r[6], "project": r[7]}
            for r in rows
        ]

    def mark_digested(self, ids: list[int]) -> None:
        if not ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.conn.executemany(
                "UPDATE events SET digested_at=? WHERE id=?",
                [(now, i) for i in ids],
            )
            self.conn.commit()
