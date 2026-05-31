# Midnight Agent Space Dashboard

Web UI for the same PostgreSQL database (`main.*`) as the Temporal worker, plus **live Temporal execution monitoring** (history → activity dots + detail panel).

## Run backend

From the **repository root**:

```powershell
pip install -r dashboard/backend/requirements.txt
python -m uvicorn dashboard.backend.main:app --reload --host 0.0.0.0 --port 8001
```

Uses `DB_*` and `TEMPORAL_*` from `temporal/.env` when present.
Quick-run execution also uses project metadata/runtime preferences `repo_path` for repository-local worktrees and artifacts.

## Run frontend

```powershell
cd dashboard/frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/ws` to the backend (`8001`).

## Features

- **Theme**: neutral black/white/grey UI with **orange** accents; main titles use **bold uppercase** + wide letter-spacing.
- **Dashboard / Projects / Documents / Tasks**: same as before (tasks remain read-only here).
- **Workflows**: DB `workflow_run` rows + **Temporal cluster** execution list; **Live →** opens the monitor when a Temporal workflow id is known or derived.
- **Live workflow** (`/workflows/live` or `/workflows/live/{workflowId}`): **WebSocket** receives a **snapshot every 2s** parsed from Temporal history (activity name, input/output summaries, status). Click a dot or list row for full detail.
- **REST**: `GET /api/temporal/executions`, `GET /api/temporal/executions/{workflow_id}/snapshot`, `GET /api/temporal/workflow-runs/{id}/target` (derive `document-serialization-{project}-{agent}` / `task-execution-…` when possible).

Child workflows with ids like `task-exec-{project}-{run_id}` are not auto-derived from DB; use the Temporal list or paste the id on the Live page.

## Editing workflow results

Still not supported from the UI (by design); tasks table is read-only for workflow output.
