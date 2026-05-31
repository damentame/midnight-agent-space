"""
FastAPI entry: run with
  uvicorn dashboard.backend.main:app --reload --host 0.0.0.0 --port 8001
from repository root.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import app_config
from .database import db_manager
from .routes import agent_runs, agentic, documents, projects, stats, tasks, temporal_routes, workflows
from .temporal_service import fetch_workflow_snapshot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_manager.initialize()
    logger.info("Dashboard API ready on port %s", app_config.api_port)
    yield
    await db_manager.close()


app = FastAPI(
    title="Midnight Agent Space Dashboard",
    description="MVP API for projects, documents, tasks, and workflow runs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(workflows.router, prefix="/api", tags=["workflows"])
app.include_router(temporal_routes.router, prefix="/api")
app.include_router(agentic.router, prefix="/api")
app.include_router(agent_runs.router, prefix="/api", tags=["agent-runs"])


@app.websocket("/ws/temporal/executions/{workflow_id}")
async def websocket_temporal_execution(websocket: WebSocket, workflow_id: str):
    """Poll Temporal history every ~2s and push JSON snapshots (activity dots + summaries)."""
    await websocket.accept()
    run_id = websocket.query_params.get("run_id")
    try:
        while True:
            try:
                snap = await fetch_workflow_snapshot(workflow_id, run_id=run_id or None)
                await websocket.send_json({"type": "snapshot", **snap})
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("websocket disconnected for workflow_id=%s", workflow_id)


@app.get("/health")
async def health():
    ok = await db_manager.health_check()
    if not ok:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"},
        )
    return {"status": "healthy", "database": "connected"}


@app.get("/api/test")
async def test_db():
    try:
        n = await db_manager.fetch_val("SELECT COUNT(*) FROM main.project")
        return {"ok": True, "project_count": int(n)}
    except Exception as e:
        logger.exception("db test failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
