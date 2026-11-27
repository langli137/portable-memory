#!/usr/bin/env python3
"""Install portable memory into one or more AI editors.

The memory body is written once and adapted to each editor's global memory
entry point. Re-running is idempotent: a managed block is replaced in place,
never appended twice. User-authored content outside the block is preserved.

Usage:
    python install.py --all
    python install.py --editors workbuddy,claude
    python install.py --editors cursor --dry-run
    python install.py --list
    python install.py --uninstall --editors workbuddy
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HOME = Path.home()
BLOCK_START = "<!-- portable-memory:START -->"
BLOCK_END = "<!-- portable-memory:END -->"


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    discover: Callable[[], Path | None]
    scope: str
    note: str


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _workbuddy() -> Path | None:
    base = HOME / ".workbuddy"
    if not base.is_dir():
        return None
    # WorkBuddy stores user memory under user-<uuid>/MEMORY.md
    candidates = sorted(base.glob("user-*/MEMORY.md"))
    return candidates[0] if candidates else None


def _claude() -> Path | None:
    base = HOME / ".claude"
    return (base / "CLAUDE.md") if base.is_dir() else None


def _cursor() -> Path | None:
    # Cursor supports both the legacy global file and the newer rules dir.
    legacy = HOME / ".cursorrules"
    if legacy.exists():
        return legacy
    rules = HOME / ".cursor" / "rules" / "portable-memory.mdc"
    return rules if rules.parent.is_dir() else None


def _codebuddy() -> Path | None:
    base = HOME / ".codebuddy" / "rules"
    return (base / "portable-memory.mdc") if base.is_dir() else None


def _copilot() -> Path | None:
    # Copilot instructions are project-scoped; this is the current project.
    p = Path.cwd() / ".github" / "copilot-instructions.md"
    return p if p.parent.is_dir() else None


def _windsurf() -> Path | None:
    legacy = HOME / ".windsurfrules"
    if legacy.exists():
        return legacy
    p = HOME / ".codeium" / "windsurf" / "global_rules.md"
    return p if p.parent.is_dir() else None


TARGETS: list[Target] = [
    Target("workbuddy", "WorkBuddy", _workbuddy, "user",
           "User-level MEMORY.md; confirmed auto-injected across projects."),
    Target("claude", "Claude Code", _claude, "user",
           "User-level CLAUDE.md; auto-injected into every session."),
    Target("cursor", "Cursor", _cursor, "user",
           "Global .cursorrules or ~/.cursor/rules/*.mdc."),
    Target("codebuddy", "CodeBuddy", _codebuddy, "user",
           "Global rules dir; verify injection in your CodeBuddy version."),
    Target("copilot", "GitHub Copilot", _copilot, "project",
           "Project-scoped; run once per repository."),
    Target("windsurf", "Windsurf", _windsurf, "user",
           "Global rules file; auto-injected."),
]


def load_body() -> str:
    path = Path(__file__).resolve().parent.parent / "references" / "memory-core.md"
    if not path.is_file():
        raise SystemExit(f"Missing memory body: {path}")
    return path.read_text(encoding="utf-8").strip()


def render(target: Target, body: str) -> str:
    if target.key == "codebuddy":
        header = (
            "---\n"
            "description: Portable long-term memory for this user\n"
            "alwaysApply: true\n"
            "enabled: true\n"
            "agent_created: true\n"
            "---\n\n"
        )
    elif target.key == "cursor" and target.key != "workbuddy":
        header = ""
    else:
        header = ""

    return (
        f"{header}{BLOCK_START}\n"
        f"<!-- managed by portable-memory; edits outside this block are preserved -->\n\n"
        f"{body}\n\n"
        f"{BLOCK_END}\n"
    )


def merge(existing: str, block: str) -> str:
    pattern = re.compile(
        re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END),
        re.DOTALL,
    )
    if pattern.search(existing):
        return pattern.sub(block.strip(), existing).rstrip() + "\n"
    if not existing.strip():
        return block
    return existing.rstrip() + "\n\n" + block


def apply(target: Target, body: str, dry_run: bool, uninstall: bool) -> str:
    path = target.discover()
    if path is None:
        return f"{target.label:<16} SKIP  (editor directory not found)"

    if uninstall:
        if not path.exists():
            return f"{target.label:<16} SKIP  (file absent)"
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(
            r"\n?" + re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?",
            re.DOTALL,
        )
        new = pattern.sub("", text)
        if not dry_run:
            path.write_text(new.lstrip("\n"), encoding="utf-8")
        return f"{target.label:<16} REMOVE  {path}"

    new_text = merge(path.read_text(encoding="utf-8") if path.exists() else "",
                     render(target, body))
    if dry_run:
        return f"{target.label:<16} WOULD WRITE  {path} ({len(new_text)} chars)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return f"{target.label:<16} OK  {path} ({len(new_text)} chars)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="install into every detected editor")
    parser.add_argument("--editors", help="comma-separated target keys")
    parser.add_argument("--list", action="store_true", help="list targets and detection status")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    parser.add_argument("--uninstall", action="store_true", help="remove managed blocks")
    args = parser.parse_args()

    if args.list:
        for t in TARGETS:
            p = t.discover()
            state = str(p) if p else "not detected"
            print(f"{t.key:<12} {t.scope:<8} {t.label:<16} {state}")
        return 0

    if not args.all and not args.editors:
        parser.error("provide --all, --editors, or --list")

    selected = TARGETS if args.all else [
        t for t in TARGETS if t.key in {x.strip() for x in args.editors.split(",")}
    ]
    unknown = {x.strip() for x in (args.editors or "").split(",")} - {t.key for t in TARGETS}
    unknown.discard("")
    if unknown:
        parser.error(f"unknown editor keys: {', '.join(sorted(unknown))}")

    body = "" if args.uninstall else load_body()
    for t in selected:
        print(apply(t, body, args.dry_run, args.uninstall))
    return 0


if __name__ == "__main__":
    sys.exit(main())
