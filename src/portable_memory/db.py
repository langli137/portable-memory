"""SQLite storage layer.

Stores one memory per row with a content hash for deduplication, access
statistics for ranking, and soft deletion so recall never returns removed
items. A plain Markdown mirror is exported on demand for human inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Memory:
    id: int
    hash: str
    content: str
    memory_type: str
    namespace: str
    source: str
    tags: list[str]
    created_at: float
    updated_at: float
    last_accessed: float
    access_count: int
    importance: float

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Memory":
        d = dict(row)
        d.pop("deleted", None)
        d["tags"] = json.loads(d.get("tags") or "[]")
        return cls(**d)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "content": self.content,
            "type": self.memory_type,
            "namespace": self.namespace,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "importance": self.importance,
        }
        return d


SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hash          TEXT NOT NULL UNIQUE,
    content       TEXT NOT NULL,
    memory_type   TEXT NOT NULL DEFAULT 'fact',
    namespace     TEXT NOT NULL DEFAULT 'default',
    source        TEXT NOT NULL DEFAULT '',
    tags          TEXT NOT NULL DEFAULT '[]',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    last_accessed REAL NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0,
    importance    REAL NOT NULL DEFAULT 1.0,
    deleted       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_memories_live
    ON memories(namespace, deleted);
CREATE INDEX IF NOT EXISTS idx_memories_hash
    ON memories(hash);
"""

# Patterns stripped before a memory is stored. This is a best-effort guard
# against accidentally persisting credentials copied from a terminal.
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
]


def content_hash(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def redact(content: str) -> tuple[str, bool]:
    """Return (clean_content, changed)."""
    clean = content
    changed = False
    for pattern in SECRET_PATTERNS:
        new, n = pattern.subn("[REDACTED]", clean)
        if n:
            changed = True
            clean = new
    return clean.strip(), changed


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        """Shared connection for companion tables (workspace)."""
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def add(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        namespace: str = "default",
        source: str = "",
        tags: Iterable[str] = (),
        importance: float = 1.0,
        allow_duplicate: bool = False,
    ) -> tuple[Memory | None, str]:
        """Insert a memory. Returns (memory, status) where status is one of
        added, duplicate, updated, redacted-only.
        """
        clean, changed = redact(content)
        if not clean:
            raise ValueError("empty memory content")
        h = content_hash(clean)
        now = time.time()
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT * FROM memories WHERE hash = ? AND deleted = 0", (h,)
        ).fetchone()
        if row:
            existing = Memory.from_row(row)
            cur.execute(
                "UPDATE memories SET access_count = access_count + 1, "
                "last_accessed = ?, importance = MAX(importance, ?) WHERE id = ?",
                (now, importance, existing.id),
            )
            self._conn.commit()
            return self.get(existing.id), "duplicate"

        if allow_duplicate:
            h = f"{h}-{now:.6f}"

        cur.execute(
            "INSERT INTO memories (hash, content, memory_type, namespace, source, "
            "tags, created_at, updated_at, last_accessed, access_count, importance, deleted) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0)",
            (
                h,
                clean,
                memory_type,
                namespace,
                source,
                json.dumps(list(tags), ensure_ascii=False),
                now,
                now,
                now,
                importance,
            ),
        )
        self._conn.commit()
        mem = self.get(cur.lastrowid)
        return mem, ("redacted" if changed else "added")

    def get(self, memory_id: int) -> Memory | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ? AND deleted = 0", (memory_id,)
        ).fetchone()
        return Memory.from_row(row) if row else None

    def all(self, namespace: str | None = None) -> list[Memory]:
        if namespace:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE deleted = 0 AND namespace = ? "
                "ORDER BY id", (namespace,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE deleted = 0 ORDER BY id"
            ).fetchall()
        return [Memory.from_row(r) for r in rows]

    def touch(self, memory_id: int) -> None:
        self._conn.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? "
            "WHERE id = ?", (time.time(), memory_id)
        )
        self._conn.commit()

    def delete(self, memory_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE memories SET deleted = 1 WHERE id = ? AND deleted = 0", (memory_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update(self, memory_id: int, content: str) -> Memory | None:
        clean, _ = redact(content)
        self._conn.execute(
            "UPDATE memories SET content = ?, hash = ?, updated_at = ? WHERE id = ?",
            (clean, content_hash(clean), time.time(), memory_id)
        )
        self._conn.commit()
        return self.get(memory_id)

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT namespace) AS namespaces, "
            "SUM(access_count) AS accesses FROM memories WHERE deleted = 0"
        ).fetchone()
        return {
            "total": row["total"],
            "namespaces": row["namespaces"],
            "total_accesses": row["accesses"] or 0,
        }

    def export_markdown(self, path: Path) -> int:
        """Write a human-readable Markdown mirror. Returns memory count."""
        mems = self.all()
        lines = [
            "# Portable memory export",
            "",
            f"> {len(mems)} memories. Generated locally; edit with care.",
            "",
        ]
        by_ns: dict[str, list[Memory]] = {}
        for m in mems:
            by_ns.setdefault(m.namespace, []).append(m)
        for ns, items in by_ns.items():
            lines += [f"## {ns}", ""]
            for m in items:
                tags = ", ".join(m.tags) if m.tags else "-"
                lines += [
                    f"### {m.id} · {m.memory_type}",
                    "",
                    m.content,
                    "",
                    f"_tags: {tags} · importance: {m.importance} · "
                    f"accesses: {m.access_count}_",
                    "",
                ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(mems)

    def import_markdown(self, path: Path, namespace: str = "imported") -> dict:
        """Import `### <id> · <type>` sections from an exported Markdown file."""
        text = path.read_text(encoding="utf-8")
        sections = re.split(r"^###\s+", text, flags=re.MULTILINE)[1:]
        added = 0
        duplicates = 0
        for section in sections:
            header, _, body = section.partition("\n")
            m = re.search(r"·\s*(\w+)", header)
            mtype = m.group(1) if m else "fact"
            body = re.sub(r"_tags:.*$", "", body, flags=re.MULTILINE).strip()
            if not body:
                continue
            _, status = self.add(
                body, memory_type=mtype, namespace=namespace, source="markdown-import"
            )
            if status == "duplicate":
                duplicates += 1
            else:
                added += 1
        return {"added": added, "duplicates": duplicates}
