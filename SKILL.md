---
name: portable-memory
description: This skill installs and maintains a cross-project "external memory" system for a user. It should be used when the user asks to remember a preference long-term, set up or update cross-project memory, install memory into an AI editor (WorkBuddy, Claude Code, Cursor, CodeBuddy, GitHub Copilot, Windsurf), or asks what personal settings are remembered. It writes a single concise memory body into the correct global entry point of each editor via scripts/install.py.
agent_created: true
---

# Portable Memory

## Overview

Maintain one concise, cross-project memory body and install it into the user's
AI editors. Project-specific facts do not belong here — they go into the
project's own memory directory. The skill is the installer and maintainer; the
memory body itself is auto-injected by the editor at session start.

## When to use

- User states a stable preference ("always do X", "never do Y", "remember Z").
- User asks to set up, reinstall, update, or remove cross-project memory.
- User asks which editors are supported or which settings are remembered.

## Decide scope before writing

Ask or infer which layer the information belongs to:

| Layer | Location | Content |
|-------|----------|---------|
| Cross-project | editor global memory | Preferences, environment facts, work habits, code principles |
| Project-only | `.ai-memory/` or `.workbuddy/memory/` in that repo | Architecture, field semantics, bug history, domain rules |

If uncertain, treat it as project-only. Never put one project's architecture
into the cross-project body.

## Workflow

### 1. Install or update

1. Read `references/memory-core.md` to see the current body.
2. To add a new preference, append it to the matching section and add a dated
   row to the change log. Keep the file concise — editors cap memory size.
3. Run the installer:

   ```bash
   python scripts/install.py --list
   python scripts/install.py --all
   # or a subset:
   python scripts/install.py --editors workbuddy,claude --dry-run
   ```

4. Report which targets were written and their paths. The installer is
   idempotent: it replaces a managed block in place and preserves text outside
   it, so re-running never duplicates content.

### 2. Uninstall

```bash
python scripts/install.py --uninstall --editors workbuddy
```

This removes only the managed block; user-authored memory stays intact.

### 3. Answer "what do you remember"

Read `references/memory-core.md` and summarize the sections. Do not invent
entries that are not in the file.

## Supported editors

| Key | Editor | Entry point | Scope |
|-----|--------|-------------|-------|
| `workbuddy` | WorkBuddy | `~/.workbuddy/user-*/MEMORY.md` | user, auto-injected |
| `claude` | Claude Code | `~/.claude/CLAUDE.md` | user, auto-injected |
| `cursor` | Cursor | `~/.cursorrules` or `~/.cursor/rules/*.mdc` | user, auto-injected |
| `codebuddy` | CodeBuddy | `~/.codebuddy/rules/*.mdc` | user, verify injection |
| `copilot` | GitHub Copilot | `.github/copilot-instructions.md` | project, run per repo |
| `windsurf` | Windsurf | `~/.windsurfrules` | user, auto-injected |

## Guardrails

- Never overwrite user-authored memory; only touch the managed block.
- Never claim memory is active in an editor that was not written.
- Keep the body under the size cap of the strictest installed editor.
