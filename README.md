# Midnight Agent Space

Local dashboard and Temporal workflows for project/document/task orchestration with agentic quick runs.

## Upgrade docs

- Phase 0-4 implementation notes: `docs/major-upgrade-phase0-4-implementation-notes.md`
- Phase 5-10 demo guide: `docs/major-upgrade-phase5-10-demo.md`

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
- `MIDNIGHT_DEFAULT_RUNTIME`
- `MIDNIGHT_MAX_CONCURRENCY`
- `MIDNIGHT_WORKTREE_BASE_PATH`
- `MIDNIGHT_RUN_ARTIFACT_PATH`

Legacy `CODEX_CLI_*` keys are still supported for backward compatibility.
