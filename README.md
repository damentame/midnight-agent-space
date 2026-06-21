# Midnight Agent Space

Local dashboard and Temporal workflows for project/document/task orchestration with agentic quick runs.

## Upgrade docs

- Phase 0-4 implementation notes: `docs/major-upgrade-phase0-4-implementation-notes.md`
- Phase 5-10 demo guide: `docs/major-upgrade-phase5-10-demo.md`

## Agent runtimes (Cursor Agent + Codex + Claude)

Install Codex and Claude CLIs used for review and fixed-mode runs:

```bash
npm run setup:clis
```

Install **Cursor Agent** separately (`cursor-agent` on PATH, or set `CURSOR_AGENT_COMMAND`).

In sidebar **Settings**, pick **Cursor Agent**, **Codex CLI**, or **Claude CLI** as the primary runtime. Enable **Balanced agent usage** to route code tasks to Cursor Agent, review tasks to your reviewer CLI (Claude by default), and run an automatic post-execution design review.

If the dashboard cannot find a binary on PATH, point `CODEX_COMMAND` / `CLAUDE_COMMAND` / `CURSOR_AGENT_COMMAND` at the correct binary (see `npm run verify:clis`).

## Quick start

1. Start backend:
   - `uvicorn dashboard.backend.main:app --reload --host 0.0.0.0 --port 8001`
2. Start frontend:
   - `cd dashboard/frontend && npm run dev`
3. Open `/projects` and run the demo flow from the Phase 5-10 guide.

## Quick-run env keys

- `CODEX_COMMAND`
- `CODEX_SANDBOX_MODE`
- `CODEX_APPROVAL_MODE`
- `CODEX_DEFAULT_TIMEOUT_SECONDS`
- `CLAUDE_COMMAND`
- `CLAUDE_CLI_MODEL`
- `CLAUDE_PERMISSION_MODE`
- `MIDNIGHT_DEFAULT_RUNTIME` (`codex-cli`, `claude-cli`, or `cursor-agent`)
- `CURSOR_AGENT_COMMAND`
- `MIDNIGHT_REVIEWER_RUNTIME` (`claude-cli` or `codex-cli`)
- `MIDNIGHT_MAX_CONCURRENCY`
- `MIDNIGHT_WORKTREE_BASE_PATH`
- `MIDNIGHT_RUN_ARTIFACT_PATH`

Legacy `CODEX_CLI_*` keys are still supported for backward compatibility.
