# PatchNoz — Branch Log

This file lists every branch chosen for a commit (or commit group).  
**Update this file on every new commit** before or as part of that change.

## Naming convention

Branches follow conventional commit style:

```
<type>/<short-kebab-description>
```

Common types: `chore`, `feat`, `fix`, `docs`, `refactor`, `test`, `ci`.

---

## Branches

| # | Branch | Related commit message | SHA (short) | Status | Notes |
|---|--------|------------------------|-------------|--------|-------|
| 1 | `chore/add-gitignore` | `chore: add .gitignore file` | `d393999` | done | Initial ignore rules for Python, venv, env secrets, IDE/OS junk |
| 2 | `feat/signoz-mcp-server` | `feat: add custom SigNoz MCP server and test client` | `61d842e` | done | Added src/mcp_server.py exposing get_recent_traces, get_recent_logs, get_metric_anomalies and scripts/test_mcp_client.py |

---

## How to update (every new commit)

1. Pick a branch name from the commit intent, e.g. `feat/send-test-trace`.
2. Append a new row to the table above (increment `#`).
3. Fill **Branch**, **Related commit message**, **SHA**, **Status**, **Notes**.
4. Mention the branch in `patchnoz.md` if the change affects project docs or layout.
5. Keep this file in sync with git history — do not skip commits.

### Status values

| Status | Meaning |
|--------|---------|
| `planned` | Branch name reserved; work not started |
| `in-progress` | Branch checked out / work ongoing |
| `done` | Commit landed (merged or on mainline history) |
| `abandoned` | Branch dropped; keep the row for history |
