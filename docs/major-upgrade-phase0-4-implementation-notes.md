# Midnight Agent Space Major Upgrade (Phase 0-4)

## Scope implemented

- Additive database schema support for:
  - project metadata
  - document version history
  - agent run/task/event/artifact tracking
  - git change tracking
  - unified change history timeline
- Backend service layer and routes for:
  - project metadata
  - document versioning
  - change history
  - run and quick-run APIs
  - runtime health/capabilities checks
- Agent assets:
  - prompt templates
  - JSON schemas for quick-run payloads, event payloads, and context packs
- Runtime skeletons:
  - Codex CLI command construction and JSON event parsing
  - context pack assembly from project/doc/version/task/change data
  - git worktree planning (create/cleanup command skeleton)
  - verification scaffolding for quick-run input and runtime readiness

## Non-goals in this phase

- No table drops or destructive data migrations.
- No Docker agent runtime implementation.
- Hermes execution remains optional and disabled by default (`HERMES_ENABLED=false`).
- No replacement/removal of existing dashboard API routes.

## Integration strategy

1. Keep all existing `/api/projects`, `/api/documents`, `/api/tasks`, `/api/workflows`, `/api/temporal` endpoints intact.
2. Add new additive endpoints in a dedicated router (`/api/agentic/*`).
3. Use lightweight service modules under `dashboard/backend/services` to avoid bloating route handlers.
4. Keep quick-runs demoable by storing run plan/context and command preview even when runtime execution is disabled/unavailable.

## Verification checklist

1. Apply SQL:
   - `MidnightAgentSpaceDB_dev/Tables/phase0_4_agentic_upgrade.sql`
   - `temporal/schema/phase0_4_agentic_upgrade.sql`
2. Start backend and call:
   - `GET /api/agentic/runtime/check`
   - `GET /api/agentic/projects/{project_id}/metadata`
   - `GET /api/agentic/projects/{project_id}/change-history`
3. Create a quick run:
   - `POST /api/agentic/quick-runs` with `dry_run=true`
4. Validate service import health:
   - `python -m compileall dashboard/backend`
