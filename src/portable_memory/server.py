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
from .workspace import Workspace

TIME_FMT = "%Y-%m-%d"


class MemoryService:
    def __init__(self, config: Config):
        self.config = config
        config.ensure_data_dir()
        self.store = Store(config.db_path)
        self.retriever = Retriever(self.store, config)
        self.workspace = Workspace(self.store.conn)

    def remember(self, payload: dict) -> dict:
        text = payload.get("content") or payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("content is required")
        namespace = payload.get("namespace") or "default"
        session_id = payload.get("session_id")
        source = payload.get("source", "")
        if session_id:
            source = f"session:{session_id}"
        self.workspace.register_project(namespace)
        mem, status = capture(
            self.store,
            text,
            memory_type=payload.get("type", "fact"),
            namespace=namespace,
            source=source,
            tags=payload.get("tags") or [],
            importance=float(payload.get("importance", 1.0)),
        )
        if session_id:
            session = self.workspace.get_session(int(session_id))
            if session:
                self.conn.execute(
                    "UPDATE sessions SET memory_count = memory_count + 1 WHERE id = ?",
                    (int(session_id),),
                )
                self.conn.commit()
        if status != "duplicate":
            self.retriever.invalidate(namespace)
        return {"status": status, "memory": mem.to_dict() if mem else None}

    @property
    def conn(self):
        return self.store.conn

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
        deleted = self.store.delete(memory_id)
        if deleted:
            self.retriever.invalidate()  # soft-delete: namespace unknown without a read
        return {"deleted": deleted, "id": memory_id}

    def export(self) -> dict:
        path = self.config.data_dir / "memory.md"
        n = self.store.export_markdown(path)
        return {"count": n, "path": str(path)}

    def seed(self, payload: dict) -> dict:
        path = Path(payload.get("path", ""))
        ns = payload.get("namespace", "default")
        result = seed_from_markdown(self.store, path, ns)
        if result.get("added"):
            self.retriever.invalidate(ns)
        return result

    def stats(self) -> dict:
        return self.store.stats()

    # ---- workspace: projects + sessions ----
    def projects(self) -> dict:
        items = [p.to_dict() for p in self.workspace.projects()]
        active = self.workspace.get_last_active()
        return {
            "count": len(items),
            "items": items,
            "active_namespace": active.namespace if active else None,
        }

    def register_project(self, payload: dict) -> dict:
        ns = payload.get("namespace")
        if not ns:
            raise ValueError("namespace is required")
        p = self.workspace.register_project(
            str(ns),
            payload.get("name", ""),
            payload.get("path", ""),
            payload.get("description", ""),
        )
        return {"project": p.to_dict()}

    def sessions(self, params: dict) -> dict:
        items = [s.to_dict() for s in self.workspace.sessions(
            params.get("namespace"), _to_int(params.get("limit"), 50)
        )]
        return {"count": len(items), "items": items}

    def session_open(self, payload: dict) -> dict:
        s = self.workspace.session_open(
            payload.get("namespace", "default"),
            payload.get("title", ""),
            payload.get("tool", ""),
        )
        return {"session": s.to_dict()}

    def session_close(self, payload: dict) -> dict:
        sid = payload.get("id")
        if sid is None:
            raise ValueError("id is required")
        mc = payload.get("memory_count")
        s = self.workspace.session_close(
            int(sid), payload.get("summary", ""),
            int(mc) if mc is not None else None,
        )
        return {"session": s.to_dict() if s else None}

    def session_delete(self, session_id: int) -> dict:
        return {"deleted": self.workspace.delete_session(session_id), "id": session_id}

    def update_memory(self, memory_id: int, payload: dict) -> dict:
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content is required")
        mem = self.store.update(memory_id, content)
        if mem:
            self.retriever.invalidate(mem.namespace)
        return {"memory": mem.to_dict() if mem else None}


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

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
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
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}

        try:
            # Web UI (static assets) — served before auth so the page can load
            # and then call the API with a token entered by the user.
            # Two versions:
            #   /ui        -> zero-dependency single-file HTML
            #   /ui/app    -> built Vue 3 workbench (src/webui/dist)
            webui = Path(__file__).parent.parent / "webui"
            if path == "/ui":
                self._send_file(webui / "index.html", "text/html; charset=utf-8")
                return
            if path == "/ui/app":
                self._send_file(webui / "dist" / "index.html", "text/html; charset=utf-8")
                return

            # Static assets. Resolve the path and verify it stays under the
            # intended root before reading — blocks ../ traversal attempts.
            if path.startswith("/ui/"):
                if path.startswith("/ui/app/"):
                    root = webui / "dist"
                    rel = path[len("/ui/app/"):]
                else:
                    root = webui
                    rel = path[len("/ui/"):]
                asset = (root / rel).resolve()
                if asset.is_file() and asset.is_relative_to(root.resolve()):
                    ctype = "text/css; charset=utf-8" if rel.endswith(".css") else \
                            "application/javascript; charset=utf-8" if rel.endswith(".js") else \
                            "application/octet-stream"
                    self._send_file(asset, ctype)
                    return
                self._send(404, {"error": "not found"})
                return

            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return

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
            elif path == "/projects":
                self._send(200, self.service.projects())
            elif path == "/projects/register" and method == "POST":
                self._send(200, self.service.register_project(self._body()))
            elif path == "/sessions":
                if method == "POST":
                    self._send(200, self.service.session_open(self._body()))
                else:
                    self._send(200, self.service.sessions(params))
            elif path == "/sessions/close" and method == "POST":
                self._send(200, self.service.session_close(self._body()))
            elif re.match(r"^/sessions/\d+$", path) and method == "DELETE":
                sid = int(path.rsplit("/", 1)[1])
                self._send(200, self.service.session_delete(sid))
            elif re.match(r"^/memory/\d+$", path):
                mid = int(path.rsplit("/", 1)[1])
                if method == "DELETE":
                    self._send(200, self.service.forget(mid))
                elif method == "PUT":
                    self._send(200, self.service.update_memory(mid, self._body()))
                else:
                    self._send(404, {"error": "not found"})
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

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")


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
