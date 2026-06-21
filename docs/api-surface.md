# Midnight Agent Space — Dashboard API Surface

Primary REST API is served by `dashboard/backend` on port **8001**. The React dashboard proxies `/api/*` to this backend.

## Projects

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/batch-summaries` | Recent projects with counts + latest run (N+1 safe) |
| GET | `/api/projects/{id}` | Project detail |
| GET | `/api/projects/{id}/summary` | Document/task/run counts |
| GET | `/api/projects/{id}/health` | Aggregated health: latest run, preview, runnable checks |
| POST | `/api/projects/{id}/refresh` | Tag snapshot + reset execution state |
| POST | `/api/projects/{id}/workspace/prepare` | Prepare local workspace |
| POST | `/api/projects/{id}/codebase/serialize` | Serialize codebase for context |
| POST | `/api/projects/{id}/analysis-plan` | Generate task board |
| GET/POST | `/api/projects/{id}/preview/*` | Detect, start, status |

## Runs (per project)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/projects/{id}/runs` | List runs |
| POST | `/api/projects/{id}/quick-runs` | Start execute |
| GET | `/api/projects/{id}/runs/{runId}` | Run detail |
| GET | `/api/projects/{id}/runs/{runId}/events` | REST events |
| GET | `/api/projects/{id}/runs/{runId}/events/stream` | SSE live events |
| POST | cancel / retry / reconcile / cleanup | Run lifecycle |

## Documents & agentic

| Method | Path | Purpose |
|--------|------|---------|
| CRUD | `/api/projects/{id}/documents` | Upload, list, patch |
| GET | `/api/projects/{id}/documents/{docId}/file` | Download (RFC 5987 unicode filenames) |
| GET | `/api/agentic/runtime/check` | CLI + git runtime health |

## Deprecated / unused in UI

- Global `/api/agentic/runs/*` — prefer project-scoped run routes above.

## Error shape

4xx/5xx may return:

```json
{ "detail": "Human message", "code": "OPTIONAL_CODE", "hint": "Actionable next step" }
```

Frontend `api.ts` surfaces `detail` and `hint` in thrown `Error` messages.
