"""sqlite 连接与 PRAGMA 管理：每工作区独立连接，WAL + NORMAL + busy_timeout。"""
from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

from app.config import StorageCfg


def _base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


MIGRATIONS_DIR = _base_dir() / "migrations"


class Database:
    def __init__(self, path: Path, storage: StorageCfg):
        self.path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"PRAGMA page_size={4096}")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA cache_size=-65536")
        cur.execute("PRAGMA mmap_size=268435456")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA wal_autocheckpoint=1000")
        cur.close()
        self._conn = conn
        return conn

    def checkpoint(self) -> None:
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            self._conn.close()
            self._conn = None

    def migrate(self) -> list[int]:
        conn = self.connect()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL)"
        )
        applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        done: list[int] = []
        if not MIGRATIONS_DIR.exists():
            return done
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(f.name.split("_", 1)[0])
            if version in applied:
                continue
            with self._lock:
                conn.executescript(f.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
                    (version, f.stem, 0),
                )
                conn.commit()
            done.append(version)
        return done

    def detect_fts5(self) -> bool:
        try:
            conn = self.connect()
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE IF EXISTS _fts5_probe")
            conn.commit()
            return True
        except sqlite3.Error:
            return False
