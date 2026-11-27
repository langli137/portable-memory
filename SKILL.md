---
name: portable-memory
description: This skill manages a local long-term memory service for the user. Use it when the user says remember this, forget that, what do you remember, search my memory, set up cross-editor memory, or asks about past preferences, decisions, and project facts. It stores and recalls memories through the portable-memory Python service via CLI or MCP tools.
agent_created: true
---

# Portable Memory

## Overview

Manage the user's cross-session, cross-project long-term memory. The memory
engine is a local Python service in this repository. It captures observations,
deduplicates and redacts them, and recalls relevant items with BM25 plus time
decay. All data stays on the user's machine.

## When to use

- "记住 / remember / 别忘了" — store a preference, decision, or pitfall.
- "之前我们定了什么 / what did we decide" — recall a past fact.
- "忘了这条 / forget" — soft-delete a memory.
- "哪个项目 / 切换项目" — list or switch project namespaces.
- "这个会话 / 开始会话 / 结束会话" — manage session lifecycle.
- "配置记忆 / 接入编辑器" — register the MCP server into editors.
- "打开面板 / 可视化" — open `http://127.0.0.1:8765/ui`.

## Project isolation

When running inside a project, namespace is auto-detected from `.pmem.json`
(walking up from cwd). Do not hardcode `default` unless no marker exists.
Create one with `python -m portable_memory init <namespace>` in the project root.
Never mix one project's architecture into another project's namespace.

## Setup check

Before first use, locate the repository (this skill's directory). The CLI is
invoked with the package on PYTHONPATH:

```bash
PYTHONPATH=<repo>/src python -m portable_memory <command>
```

Windows PowerShell:
```powershell
$env:PYTHONPATH="<repo>\src"; python -m portable_memory <command>
```

If the MCP server is registered, prefer the `memory_add` / `memory_recall`
tools; otherwise fall back to the CLI.

## Workflow

### Store

```bash
python -m portable_memory remember "内容" --type rule --tags "标签" --namespace default
```

Types: `fact`, `preference`, `rule`, `decision`, `environment`, `pitfall`.
Report the returned `status`: `added`, `duplicate`, or `redacted`.

### Recall

```bash
python -m portable_memory recall "查询词" --limit 8
```

Recall at the start of a task when past context may matter. Results include
score details — use them to judge relevance, do not blindly follow every item.

### Delete / list / stats / export

```bash
python -m portable_memory forget <id>
python -m portable_memory list --namespace default
python -m portable_memory stats
python -m portable_memory export
```

### Register into editors

```bash
python scripts/setup_editors.py --all --dry-run
python scripts/setup_editors.py --all
```

Supported: Claude Code, Cursor, Windsurf, WorkBuddy, DeepSeek Harness, Copilot.

## Scope rule

- Cross-project preferences, environment facts, work habits → memory service.
- One project's architecture, field semantics, bug history → that project's
  own memory directory (`.ai-memory/` or `.workbuddy/memory/`).

Never store one project's architecture into cross-project memory.

## Guardrails

- The service redacts secrets on write, but still avoid storing credentials.
- Soft-delete is reversible only via direct DB access; confirm before deleting.
- If the engine is unreachable, say so; do not fabricate memories.
