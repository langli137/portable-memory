"""MCP stdio bridge.

Implements a minimal JSON-RPC 2.0 MCP server over stdin/stdout so any MCP
client (Claude Code, Cursor, DeepSeek Harness, etc.) can call the memory
engine as native tools. Transport is line-delimited JSON for simplicity.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import Config
from .db import Store
from .pipeline import Retriever, capture

TOOLS = [
    {
        "name": "memory_add",
        "description": "Store a long-term memory (preference, decision, fact, pitfall).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory text"},
                "type": {"type": "string", "enum": ["fact", "preference", "rule",
                                                    "decision", "environment", "pitfall"]},
                "namespace": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "importance": {"type": "number"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Search long-term memory. Use at session start and when a past decision matters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "namespace": {"type": "string"},
                "limit": {"type": "integer"},
                "since": {"type": "string", "description": "YYYY-MM-DD"},
                "until": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_list",
        "description": "List stored memories, optionally filtered by namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {"namespace": {"type": "string"}},
        },
    },
    {
        "name": "memory_delete",
        "description": "Soft-delete a memory by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
]


class MCPBridge:
    def __init__(self, config: Config):
        self.store = Store(config.db_path)
        self.retriever = Retriever(self.store, config)

    def dispatch(self, name: str, args: dict) -> dict:
        if name == "memory_add":
            mem, status = capture(
                self.store,
                args["content"],
                memory_type=args.get("type", "fact"),
                namespace=args.get("namespace", "default"),
                tags=args.get("tags", []),
                importance=float(args.get("importance", 1.0)),
                source="mcp",
            )
            return {"status": status, "memory": mem.to_dict() if mem else None}
        if name == "memory_recall":
            from .server import _parse_date
            items = self.retriever.recall(
                args.get("query", ""),
                namespace=args.get("namespace"),
                limit=int(args.get("limit", 8)),
                since=_parse_date(args.get("since")),
                until=_parse_date(args.get("until")),
            )
            return {"count": len(items), "items": [s.to_dict() for s in items]}
        if name == "memory_list":
            mems = self.store.all(args.get("namespace"))
            return {"count": len(mems), "items": [m.to_dict() for m in mems]}
        if name == "memory_delete":
            return {"deleted": self.store.delete(int(args["id"]))}
        raise ValueError(f"unknown tool: {name}")

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "portable-memory", "version": "0.1.0"},
            }}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = msg.get("params") or {}
            try:
                result = self.dispatch(params.get("name", ""), params.get("arguments") or {})
                return {"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                }}
            except Exception as exc:  # noqa: BLE001
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": str(exc)}}
        if method == "notifications/initialized" or method.startswith("notifications/"):
            return None
        if mid is not None:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": "method not found"}}
        return None


def run(config: Config) -> None:
    bridge = MCPBridge(config)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        response = bridge.handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
