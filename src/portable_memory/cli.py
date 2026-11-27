"""Command-line entry point: python -m portable_memory <command>."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import Config
from .db import Store
from .mcp import run as run_mcp
from .pipeline import Retriever, capture, seed_from_markdown
from .server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmem", description="portable-memory: local cross-editor long-term memory"
    )
    parser.add_argument("--version", action="version", version=f"pmem {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="Run the local HTTP service")
    p = sub.add_parser("mcp", help="Run the MCP stdio bridge")

    p = sub.add_parser("remember", help="Store a memory")
    p.add_argument("content")
    p.add_argument("--type", default="fact")
    p.add_argument("--namespace", default="default")
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

    p = sub.add_parser("export", help="Export memories to Markdown")
    p = sub.add_parser("seed", help="Import a Markdown seed template")
    p.add_argument("path")
    p.add_argument("--namespace", default="default")
    p = sub.add_parser("stats", help="Show memory statistics")

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
    try:
        if args.command == "remember":
            tags = [t for t in args.tags.split(",") if t]
            mem, status = capture(
                store, args.content, memory_type=args.type,
                namespace=args.namespace, tags=tags, importance=args.importance,
                source="cli",
            )
            print(json.dumps({"status": status, "memory": mem.to_dict() if mem else None},
                             ensure_ascii=False, indent=2))
        elif args.command == "recall":
            retriever = Retriever(store, config)
            items = retriever.recall(args.query, namespace=args.namespace, limit=args.limit)
            print(json.dumps({"count": len(items), "items": [s.to_dict() for s in items]},
                             ensure_ascii=False, indent=2))
        elif args.command == "list":
            mems = store.all(args.namespace)
            if args.type:
                mems = [m for m in mems if m.memory_type == args.type]
            print(json.dumps({"count": len(mems), "items": [m.to_dict() for m in mems]},
                             ensure_ascii=False, indent=2))
        elif args.command == "forget":
            print(json.dumps({"deleted": store.delete(args.id), "id": args.id}))
        elif args.command == "export":
            path = config.data_dir / "memory.md"
            n = store.export_markdown(path)
            print(json.dumps({"count": n, "path": str(path)}, ensure_ascii=False))
        elif args.command == "seed":
            print(json.dumps(seed_from_markdown(store, args.path, args.namespace),
                             ensure_ascii=False))
        elif args.command == "stats":
            print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
