#!/usr/bin/env python3
"""Register the portable-memory MCP server into AI editors.

Two scopes:

  * Global (default): one config per editor in the home directory. The MCP
    process discovers the project by walking up from cwd to .pmem.json.
  * Project (--project): writes an editor-specific config inside a project,
    injecting PMEM_NAMESPACE so the MCP process knows its project regardless
    of where the editor was launched from. This is the reliable mode.

Idempotent: only the managed `portable-memory` entry is rewritten.

Usage:
    python scripts/setup_editors.py --list
    python scripts/setup_editors.py --all --dry-run
    python scripts/setup_editors.py --all --project /path/to/project
    python scripts/setup_editors.py --editors claude --project . --namespace my-app
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


def _mcp_entry(namespace: str | None = None) -> dict:
    env = {
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        "PMEM_DATA_DIR": os.environ.get(
            "PMEM_DATA_DIR", str(HOME / ".portable-memory")
        ),
    }
    if namespace:
        env["PMEM_NAMESPACE"] = namespace
    return {
        "command": _python_cmd(),
        "args": ["-m", "portable_memory", "mcp"],
        "env": env,
    }


def _merge_mcp(existing: dict, dry_run: bool, path: Path, namespace: str | None) -> str:
    data = existing.get("mcpServers", {}) if isinstance(existing, dict) else {}
    data["portable-memory"] = _mcp_entry(namespace)
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged["mcpServers"] = data
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    suffix = f" (namespace={namespace})" if namespace else ""
    return f"OK  {path}{suffix}"


def _write(existing: dict, dry: bool, path: Path, ns: str | None) -> str:
    return _merge_mcp(existing, dry, path, ns)


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


# ---- Global scope: one config per editor in HOME ----

def claude_global(root: Path, dry: bool, ns: str | None) -> str:
    return _write(_load(HOME / ".claude.json"), dry, HOME / ".claude.json", ns)


def cursor_global(root: Path, dry: bool, ns: str | None) -> str:
    p = HOME / ".cursor" / "mcp.json"
    return _write(_load(p), dry, p, ns)


def windsurf_global(root: Path, dry: bool, ns: str | None) -> str:
    p = HOME / ".codeium" / "windsurf" / "mcp_config.json"
    return _write(_load(p), dry, p, ns)


def workbuddy_global(root: Path, dry: bool, ns: str | None) -> str:
    p = HOME / ".workbuddy" / "mcp.json"
    return _write(_load(p), dry, p, ns)


def dsh_global(root: Path, dry: bool, ns: str | None) -> str:
    p = HOME / ".dsh" / "config.json"
    return _write(_load(p), dry, p, ns)


# ---- Project scope: config inside the repo, namespace pinned ----

def claude_project(root: Path, dry: bool, ns: str | None) -> str:
    p = root / ".mcp.json"
    return _write(_load(p), dry, p, ns)


def cursor_project(root: Path, dry: bool, ns: str | None) -> str:
    p = root / ".cursor" / "mcp.json"
    return _write(_load(p), dry, p, ns)


def windsurf_project(root: Path, dry: bool, ns: str | None) -> str:
    p = root / ".windsurf" / "mcp.json"
    return _write(_load(p), dry, p, ns)


def workbuddy_project(root: Path, dry: bool, ns: str | None) -> str:
    p = root / ".workbuddy" / "mcp.json"
    return _write(_load(p), dry, p, ns)


def dsh_project(root: Path, dry: bool, ns: str | None) -> str:
    p = root / ".dsh" / "config.json"
    return _write(_load(p), dry, p, ns)


def copilot_project(root: Path, dry: bool, ns: str | None) -> str:
    p = root / ".vscode" / "mcp.json"
    return _write(_load(p), dry, p, ns)


GLOBAL: dict[str, Callable[[Path, bool, str | None], str]] = {
    "claude": claude_global,
    "cursor": cursor_global,
    "windsurf": windsurf_global,
    "workbuddy": workbuddy_global,
    "dsh": dsh_global,
}

PROJECT: dict[str, Callable[[Path, bool, str | None], str]] = {
    "claude": claude_project,
    "cursor": cursor_project,
    "windsurf": windsurf_project,
    "workbuddy": workbuddy_project,
    "dsh": dsh_project,
    "copilot": copilot_project,
}

DESCRIPTIONS = {
    "claude": "Claude Code",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "workbuddy": "WorkBuddy",
    "dsh": "DeepSeek Harness",
    "copilot": "GitHub Copilot",
}


def _detect_namespace(root: Path) -> str | None:
    marker = root / ".pmem.json"
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            return data.get("namespace")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--editors", help="comma-separated editor keys")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--project", metavar="PATH",
                        help="write project-level configs into PATH (pins namespace)")
    parser.add_argument("--namespace",
                        help="namespace to pin (default: read from .pmem.json)")
    args = parser.parse_args()

    if args.list:
        for key, desc in DESCRIPTIONS.items():
            print(f"{key:<10} {desc}")
        print("\nGlobal: one config per editor in HOME (cwd-based detection)")
        print("Project: config in repo, PMEM_NAMESPACE pinned (recommended)")
        return 0
    if not args.all and not args.editors:
        parser.error("provide --all, --editors, or --list")

    registry = PROJECT if args.project else GLOBAL
    keys = list(registry) if args.all else [k.strip() for k in args.editors.split(",")]
    unknown = [k for k in keys if k not in registry]
    if unknown:
        parser.error(f"unknown editors for this scope: {', '.join(unknown)}")

    root = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
    ns = args.namespace
    if args.project and not ns:
        ns = _detect_namespace(root)
        if not ns:
            parser.error("project mode needs --namespace or a .pmem.json with namespace")

    for key in keys:
        print(f"{key:<10} {registry[key](root, args.dry_run, ns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
