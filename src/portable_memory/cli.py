"""Command-line entry point: python -m portable_memory <command>."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import Config
from .db import Store
from .mcp import run as run_mcp
from .pipeline import Retriever, capture, seed_from_markdown
from .server import serve
from .workspace import Workspace


def _resolve_namespace(args, ws: Workspace) -> str:
    """CLI default: use explicit --namespace, else detect .pmem.json."""
    ns = getattr(args, "namespace", None)
    if ns:
        return ns
    detected = ws.detect_project(Path.cwd())
    return detected[0] if detected else "default"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmem", description="portable-memory: local cross-editor long-term memory"
    )
    parser.add_argument("--version", action="version", version=f"pmem {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the local HTTP service")
    sub.add_parser("mcp", help="Run the MCP stdio bridge")

    p = sub.add_parser("init", help="Create .pmem.json in this directory")
    p.add_argument("namespace", nargs="?", help="project namespace (default: dir name)")
    p.add_argument("--name", default="", help="display name")
    p.add_argument("--description", default="")
    p.add_argument("--dir", default=".", help="target directory")

    p = sub.add_parser("project", help="List / register projects")
    p.add_argument("action", nargs="?", default="list", choices=["list", "add"])
    p.add_argument("--namespace")
    p.add_argument("--name", default="")
    p.add_argument("--path", default="")

    p = sub.add_parser("session", help="Manage sessions")
    p.add_argument("action", choices=["start", "list", "close"])
    p.add_argument("--id", type=int, help="session id for close")
    p.add_argument("--namespace")
    p.add_argument("--title", default="")
    p.add_argument("--tool", default="")
    p.add_argument("--summary", default="")

    p = sub.add_parser("remember", help="Store a memory")
    p.add_argument("content")
    p.add_argument("--type", default="fact")
    p.add_argument("--namespace")
    p.add_argument("--session", type=int, help="associate with session id")
    p.add_argument("--tags", default="")
    p.add_argument("--importance", type=float, default=1.0)

    p = sub.add_parser("recall", help="Search memories")
    p.add_argument("query")
    p.add_argument("--namespace")
    p.add_argument("--limit", type=int, default=8)

    p = sub.add_parser("list", help="List memories")
    p.add_argument("--namespace")
    p.add_argument("--type")

    p = sub.add_parser("forget", help="Soft-delete a memory")
    p.add_argument("id", type=int)

    sub.add_parser("export", help="Export memories to Markdown")

    p = sub.add_parser("seed", help="Import a Markdown seed template")
    p.add_argument("path")
    p.add_argument("--namespace")

    sub.add_parser("stats", help="Show memory statistics")

    args = parser.parse_args(argv)
    config = Config.from_env()

    if args.command == "serve":
        serve(config)
        return 0
    if args.command == "mcp":
        run_mcp(config)
        return 0

    config.ensure_data_dir()
    store = Store(config.db_path)
    ws = Workspace(store.conn)
    try:
        if args.command == "init":
            directory = Path(args.dir).expanduser().resolve()
            ns = args.namespace or directory.name
            marker = ws.write_marker(
                directory, ns, args.name or ns, args.description
            )
            ws.register_project(ns, args.name or ns, str(directory), args.description)
            print(json.dumps(
                {"status": "ok", "marker": str(marker), "namespace": ns},
                ensure_ascii=False, indent=2,
            ))

        elif args.command == "project":
            if args.action == "add":
                p = ws.register_project(
                    args.namespace, args.name, args.path
                )
                print(json.dumps({"project": p.to_dict()}, ensure_ascii=False, indent=2))
            else:
                items = [p.to_dict() for p in ws.projects()]
                print(json.dumps(
                    {"count": len(items), "items": items}, ensure_ascii=False, indent=2
                ))

        elif args.command == "session":
            if args.action == "start":
                ns = _resolve_namespace(args, ws)
                s = ws.session_open(ns, args.title, args.tool)
                print(json.dumps({"session": s.to_dict()}, ensure_ascii=False, indent=2))
            elif args.action == "list":
                ns = _resolve_namespace(args, ws)
                items = [s.to_dict() for s in ws.sessions(ns)]
                print(json.dumps(
                    {"count": len(items), "items": items}, ensure_ascii=False, indent=2
                ))
            else:
                if args.id is None:
                    parser.error("session close requires --id")
                s = ws.session_close(args.id, args.summary)
                print(json.dumps({"session": s.to_dict() if s else None},
                                 ensure_ascii=False, indent=2))

        elif args.command == "remember":
            ns = _resolve_namespace(args, ws)
            ws.register_project(ns)
            tags = [t for t in args.tags.split(",") if t]
            source = f"session:{args.session}" if args.session else "cli"
            mem, status = capture(
                store, args.content, memory_type=args.type,
                namespace=ns, tags=tags, importance=args.importance, source=source,
            )
            if args.session:
                store.conn.execute(
                    "UPDATE sessions SET memory_count = memory_count + 1 WHERE id = ?",
                    (args.session,),
                )
                store.conn.commit()
            print(json.dumps({"status": status, "namespace": ns,
                              "memory": mem.to_dict() if mem else None},
                             ensure_ascii=False, indent=2))

        elif args.command == "recall":
            ns = _resolve_namespace(args, ws)
            items = Retriever(store, config).recall(
                args.query, namespace=ns, limit=args.limit
            )
            print(json.dumps({"namespace": ns, "count": len(items),
                              "items": [s.to_dict() for s in items]},
                             ensure_ascii=False, indent=2))

        elif args.command == "list":
            ns = _resolve_namespace(args, ws)
            mems = store.all(ns)
            if args.type:
                mems = [m for m in mems if m.memory_type == args.type]
            print(json.dumps({"namespace": ns, "count": len(mems),
                              "items": [m.to_dict() for m in mems]},
                             ensure_ascii=False, indent=2))

        elif args.command == "forget":
            print(json.dumps({"deleted": store.delete(args.id), "id": args.id}))

        elif args.command == "export":
            path = config.data_dir / "memory.md"
            n = store.export_markdown(path)
            print(json.dumps({"count": n, "path": str(path)}, ensure_ascii=False))

        elif args.command == "seed":
            ns = _resolve_namespace(args, ws)
            print(json.dumps(seed_from_markdown(store, args.path, ns),
                             ensure_ascii=False))

        elif args.command == "stats":
            print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
