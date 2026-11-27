#!/usr/bin/env python3
"""Register the portable-memory MCP server into AI editors.

Idempotent: re-running rewrites only the managed entry. Each editor gets an
MCP config pointing at `python -m portable_memory mcp`, which speaks MCP over
stdio using the same memory store as the REST service.

Usage:
    python scripts/setup_editors.py --list
    python scripts/setup_editors.py --all --repo-root /path/to/project
    python scripts/setup_editors.py --editors claude,cursor --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

HOME = Path.home()


def _python_cmd() -> str:
    return os.environ.get("PMEM_PYTHON", sys.executable)


def _mcp_entry() -> dict:
    return {
        "command": _python_cmd(),
        "args": ["-m", "portable_memory", "mcp"],
        "env": {
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
            "PMEM_DATA_DIR": os.environ.get(
                "PMEM_DATA_DIR", str(HOME / ".portable-memory")
            ),
        },
    }


def _merge_mcp(existing: dict, dry_run: bool, path: Path) -> str:
    data = existing.get("mcpServers", {}) if isinstance(existing, dict) else {}
    data["portable-memory"] = _mcp_entry()
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged["mcpServers"] = data
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return f"OK  {path}"


def claude(repo_root: Path | None, dry: bool) -> str:
    path = HOME / ".claude.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _merge_mcp(existing, dry, path)


def cursor(repo_root: Path | None, dry: bool) -> str:
    path = HOME / ".cursor" / "mcp.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _merge_mcp(existing, dry, path)


def windsurf(repo_root: Path | None, dry: bool) -> str:
    path = HOME / ".codeium" / "windsurf" / "mcp_config.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _merge_mcp(existing, dry, path)


def workbuddy(repo_root: Path | None, dry: bool) -> str:
    path = HOME / ".workbuddy" / "mcp.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if "mcpServers" not in existing:
        existing["mcpServers"] = {}
    return _merge_mcp(existing, dry, path)


def dsh(repo_root: Path | None, dry: bool) -> str:
    # DeepSeek Harness reads config from ~/.dsh/config.json (headless profile).
    path = HOME / ".dsh" / "config.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _merge_mcp(existing, dry, path)


def copilot(repo_root: Path | None, dry: bool) -> str:
    if repo_root is None:
        return "SKIP  copilot requires --repo-root"
    path = repo_root / ".vscode" / "mcp.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _merge_mcp(existing, dry, path)


EDITORS: dict[str, Callable[[Path | None, bool], str]] = {
    "claude": claude,
    "cursor": cursor,
    "windsurf": windsurf,
    "workbuddy": workbuddy,
    "dsh": dsh,
    "copilot": copilot,
}

DESCRIPTIONS = {
    "claude": "Claude Code (~/.claude.json)",
    "cursor": "Cursor (~/.cursor/mcp.json)",
    "windsurf": "Windsurf (~/.codeium/windsurf/mcp_config.json)",
    "workbuddy": "WorkBuddy (~/.workbuddy/mcp.json)",
    "dsh": "DeepSeek Harness (~/.dsh/config.json)",
    "copilot": "GitHub Copilot (<repo>/.vscode/mcp.json)",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--editors", help="comma-separated editor keys")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repo-root", help="project path for project-scoped editors")
    args = parser.parse_args()

    if args.list:
        for key, desc in DESCRIPTIONS.items():
            print(f"{key:<10} {desc}")
        return 0
    if not args.all and not args.editors:
        parser.error("provide --all, --editors, or --list")

    keys = list(EDITORS) if args.all else [k.strip() for k in args.editors.split(",")]
    unknown = [k for k in keys if k not in EDITORS]
    if unknown:
        parser.error(f"unknown editors: {', '.join(unknown)}")

    repo = Path(args.repo_root).expanduser().resolve() if args.repo_root else None
    for key in keys:
        print(f"{key:<10} {EDITORS[key](repo, args.dry_run)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
