"""Workspace layer: projects and sessions.

A project maps 1:1 to a memory namespace. A session belongs to a project and
records one collaboration run. Memories can optionally link to a session via
their `source` field (`session:<id>`), keeping the core memories table lean.

This module owns its own tables so the already-stable db.py stays untouched.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Project:
    namespace: str
    name: str
    path: str
    description: str
    created_at: float
    last_active: float

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "path": self.path,
            "description": self.description,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


@dataclass
class Session:
    id: int
    project: str
    title: str
    tool: str
    started_at: float
    ended_at: float | None
    summary: str
    memory_count: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Session":
        d = dict(row)
        return cls(**d)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "title": self.title,
            "tool": self.tool,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "summary": self.summary,
            "memory_count": self.memory_count,
        }


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    namespace     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    last_active   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project       TEXT NOT NULL DEFAULT 'default',
    title         TEXT NOT NULL DEFAULT '',
    tool          TEXT NOT NULL DEFAULT '',
    started_at    REAL NOT NULL,
    ended_at      REAL,
    summary       TEXT NOT NULL DEFAULT '',
    memory_count  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_project
    ON sessions(project, started_at);
"""

MARKER = ".pmem.json"


class Workspace:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- projects ----
    def register_project(
        self,
        namespace: str,
        name: str = "",
        path: str = "",
        description: str = "",
    ) -> Project:
        now = time.time()
        row = self.conn.execute(
            "SELECT * FROM projects WHERE namespace = ?", (namespace,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE projects SET name = ?, path = ?, description = ?, "
                "last_active = ? WHERE namespace = ?",
                (name or row["name"], path or row["path"],
                 description or row["description"], now, namespace),
            )
        else:
            self.conn.execute(
                "INSERT INTO projects (namespace, name, path, description, "
                "created_at, last_active) VALUES (?, ?, ?, ?, ?, ?)",
                (namespace, name or namespace, path, description, now, now),
            )
        self.conn.commit()
        return self.get_project(namespace)

    def get_project(self, namespace: str) -> Project | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE namespace = ?", (namespace,)
        ).fetchone()
        return Project(**dict(row)) if row else None

    def projects(self) -> list[Project]:
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY last_active DESC"
        ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def touch_project(self, namespace: str) -> None:
        self.conn.execute(
            "UPDATE projects SET last_active = ? WHERE namespace = ?",
            (time.time(), namespace),
        )
        self.conn.commit()

    # ---- sessions ----
    def session_open(
        self, project: str, title: str = "", tool: str = ""
    ) -> Session:
        self.register_project(project)
        cur = self.conn.execute(
            "INSERT INTO sessions (project, title, tool, started_at, "
            "ended_at, summary, memory_count) VALUES (?, ?, ?, ?, NULL, '', 0)",
            (project, title or f"session-{int(time.time())}", tool, time.time()),
        )
        self.conn.commit()
        return self.get_session(cur.lastrowid)

    def get_session(self, session_id: int) -> Session | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return Session.from_row(row) if row else None

    def session_close(
        self, session_id: int, summary: str = "", memory_count: int | None = None
    ) -> Session | None:
        # memory_count is accumulated by remember; only overwrite when a
        # caller explicitly supplies a value (e.g. reconciliation from UI).
        if memory_count is None:
            self.conn.execute(
                "UPDATE sessions SET ended_at = ?, summary = ? WHERE id = ?",
                (time.time(), summary, session_id),
            )
        else:
            self.conn.execute(
                "UPDATE sessions SET ended_at = ?, summary = ?, memory_count = ? "
                "WHERE id = ?",
                (time.time(), summary, memory_count, session_id),
            )
        self.conn.commit()
        return self.get_session(session_id)

    def sessions(self, project: str | None = None, limit: int = 50) -> list[Session]:
        if project:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE project = ? "
                "ORDER BY started_at DESC LIMIT ?", (project, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Session.from_row(r) for r in rows]

    def delete_session(self, session_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- project marker discovery ----
    @staticmethod
    def detect_project(start: Path | None = None) -> tuple[str, Path] | None:
        """Walk up from `start` looking for a .pmem.json marker."""
        current = (start or Path.cwd()).resolve()
        for candidate in [current, *current.parents]:
            marker = candidate / MARKER
            if marker.is_file():
                try:
                    data = json.loads(marker.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                ns = data.get("namespace")
                if ns:
                    return str(ns), candidate
        return None

    @staticmethod
    def write_marker(
        directory: Path, namespace: str, name: str = "", description: str = ""
    ) -> Path:
        path = (directory / MARKER).resolve()
        data = {
            "namespace": namespace,
            "name": name or namespace,
            "description": description,
        }
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path
