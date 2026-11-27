# dsh-portable-memory

DeepSeek Harness adapter for the portable-memory service.

This directory is the **upper layer** of the two-layer architecture. It contains
only glue code that forwards DSH session events to the portable-memory engine
via MCP tools. All storage, ranking, deduplication and governance live in the
Python service under `src/`, so swapping the underlying engine never requires
touching DSH-specific code.

## Status

Adapter scaffold. Implements the DSH plugin manifest and a thin bridge. Before
publishing to the DSH plugin registry, verify against the pinned DSH version:

```bash
npx -y @deepseek-ai/dsh plugin add <this-repo>/dsh-plugin
```

## Design contract

- On `turn/end`: read the session transcript, extract candidate facts, call
  `memory_add` for each accepted fact (with `source: dsh`).
- On `agent/pre-step`: call `memory_recall` with the current user request and
  inject top results as context, tagged with their ids for traceability.
- Never let the model mutate storage directly. Emit candidate operations and
  let the provider validate them.

## Configuration

`dsh.config.json` points at the MCP stdio process:

```json
{
  "command": "python",
  "args": ["-m", "portable_memory", "mcp"]
}
```

Run `python scripts/setup_editors.py --editors dsh` to register this
automatically.
