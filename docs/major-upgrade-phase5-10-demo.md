# Midnight Agent Space Major Upgrade (Phase 5-10)

## What this phase adds

- Project-scoped API surface:
  - `GET/POST /api/projects`
  - `PATCH /api/projects/{project_id}`
  - `POST /api/projects/{project_id}/archive`
  - `GET /api/projects/{project_id}/summary`
  - nested documents, runs, quick-runs, and runtime settings routes
- Real run lifecycle:
  - start/cancel/retry
  - persisted run events and SSE stream (`/events/stream`)
  - artifact capture, git change snapshots, deterministic review checks
- Codex CLI execution shape:
  - uses `codex exec` with `--json`, configured `CODEX_APPROVAL_MODE` + `CODEX_SANDBOX_MODE`, and `--cd`
  - optional `--output-schema` and `-o`
  - feature detection + fallback for older CLI shapes
- Frontend demo UI:
  - projects search/filter/edit/archive
  - project detail tabs (Overview/Documents/Runs/Tasks/Change History/Settings)
  - document viewer/editor with version creation
  - quick run form and run detail page (events/artifacts/changes/verification)

## Demo flow

1. Apply additive schema migration:
   - `MidnightAgentSpaceDB_dev/Tables/phase0_4_agentic_upgrade.sql`
2. Seed demo data:
   - `python -m dashboard.backend.scripts.seed_demo_data`
   - or run `MidnightAgentSpaceDB_dev/Tables/phase5_10_demo_seed.sql`
3. Start backend:
   - `uvicorn dashboard.backend.main:app --reload --host 0.0.0.0 --port 8001`
4. Start frontend:
   - `cd dashboard/frontend && npm run dev`
5. Open the dashboard and use:
   - `Projects` page for filtering and archiving
   - `Project Detail -> Runs` to plan/execute quick runs
   - `Run Detail` to watch SSE events and review artifacts

## New prompt/schema assets

- Prompts:
  - `planner_prompt`
  - `executor_prompt`
  - `reviewer_prompt`
- Schemas:
  - `planner`
  - `task`
  - `review`

## Notes

- Migrations are additive only.
- Runtime execution is safe-by-default via dry-run planning unless execution is explicitly requested.
- Quick-run execution requires a project-local repository path in metadata/runtime preferences (`repo_path`).
- Defaults:
  - worktrees: `repo/.midnight/worktrees/{project_id}/{run_id}` (or `MIDNIGHT_WORKTREE_BASE_PATH`)
  - run artifacts: `repo/.midnight/runs/{run_id}` (or `MIDNIGHT_RUN_ARTIFACT_PATH`)
- Generated outputs (`dist`, `node_modules`, logs, `__pycache__`) should not be committed.
