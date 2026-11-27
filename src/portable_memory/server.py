"""Local HTTP service exposing the memory engine over REST.

Uses only the standard library so the project runs with zero third-party
packages. Binds to 127.0.0.1 by default; set PMEM_TOKEN to require a Bearer
token. Endpoints are deliberately small and JSON-in/JSON-out.
"""

from __future__ import annotations

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import Config
from .db import Store
from .pipeline import Retriever, capture, seed_from_markdown

TIME_FMT = "%Y-%m-%d"


class MemoryService:
    def __init__(self, config: Config):
        self.config = config
        config.ensure_data_dir()
        self.store = Store(config.db_path)
        self.retriever = Retriever(self.store, config)

    def remember(self, payload: dict) -> dict:
        text = payload.get("content") or payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("content is required")
        mem, status = capture(
            self.store,
            text,
            memory_type=payload.get("type", "fact"),
            namespace=payload.get("namespace", "default"),
            source=payload.get("source", ""),
            tags=payload.get("tags") or [],
            importance=float(payload.get("importance", 1.0)),
        )
        return {"status": status, "memory": mem.to_dict() if mem else None}

    def recall(self, params: dict) -> dict:
        query = params.get("query") or params.get("q") or ""
        since = _parse_date(params.get("since"))
        until = _parse_date(params.get("until"))
        limit = _to_int(params.get("limit"), self.config.default_limit)
        items = self.retriever.recall(
            str(query),
            namespace=params.get("namespace"),
            memory_type=params.get("type"),
            limit=limit,
            since=since,
            until=until,
        )
        return {"count": len(items), "items": [s.to_dict() for s in items]}

    def list(self, params: dict) -> dict:
        mems = self.store.all(params.get("namespace"))
        if params.get("type"):
            mems = [m for m in mems if m.memory_type == params["type"]]
        return {"count": len(mems), "items": [m.to_dict() for m in mems]}

    def forget(self, memory_id: int) -> dict:
        return {"deleted": self.store.delete(memory_id), "id": memory_id}

    def export(self) -> dict:
        path = self.config.data_dir / "memory.md"
        n = self.store.export_markdown(path)
        return {"count": n, "path": str(path)}

    def seed(self, payload: dict) -> dict:
        path = Path(payload.get("path", ""))
        return seed_from_markdown(self.store, path, payload.get("namespace", "default"))

    def stats(self) -> dict:
        return self.store.stats()


def _parse_date(value: Any) -> float | None:
    if not value:
        return None
    try:
        return time.mktime(time.strptime(str(value), TIME_FMT))
    except ValueError:
        return None


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Handler(BaseHTTPRequestHandler):
    service: MemoryService

    def log_message(self, fmt: str, *args) -> None:
        # Keep logs quiet; write to stderr only for errors.
        pass

    def _authorized(self) -> bool:
        token = self.service.config.token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {token}"

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        raw = self.rfile.read(length)
        last_error: Exception | None = None
        for encoding in ("utf-8", "gbk"):
            try:
                value = json.loads(raw.decode(encoding))
                return value if isinstance(value, dict) else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
        raise ValueError(f"invalid JSON body: {last_error}")

    def _handle(self, method: str) -> None:
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}

        try:
            if path == "/health":
                self._send(200, {"ok": True, "version": "0.1.0"})
            elif path == "/remember" and method == "POST":
                self._send(200, self.service.remember(self._body()))
            elif path == "/recall":
                self._send(200, self.service.recall(params))
            elif path == "/list":
                self._send(200, self.service.list(params))
            elif path == "/stats":
                self._send(200, self.service.stats())
            elif path == "/export" and method == "POST":
                self._send(200, self.service.export())
            elif path == "/seed" and method == "POST":
                self._send(200, self.service.seed(self._body()))
            elif re.match(r"^/memory/\d+$", path) and method == "DELETE":
                mid = int(path.rsplit("/", 1)[1])
                self._send(200, self.service.forget(mid))
            else:
                self._send(404, {"error": "not found"})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - service must not crash
            self._send(500, {"error": str(exc)})

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")


def serve(config: Config) -> None:
    Handler.service = MemoryService(config)
    server = ThreadingHTTPServer((config.host, config.port), Handler)
    print(f"portable-memory listening on http://{config.host}:{config.port}")
    print(f"data dir: {config.data_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()
        Handler.service.store.close()
