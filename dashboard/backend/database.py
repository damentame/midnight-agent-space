"""
asyncpg pool and query helpers for main schema.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import asyncpg

from .config import db_config, get_database_dsn

logger = logging.getLogger(__name__)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    return obj


class DatabaseManager:
    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            get_database_dsn(),
            min_size=db_config.min_connections,
            max_size=db_config.max_connections,
            server_settings={"search_path": "main", "application_name": "mas_dashboard"},
        )
        async with self._pool.acquire() as conn:
            v = await conn.fetchval("SELECT version()")
            logger.info("Connected: %s", v[:60])

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        if self._pool is None:
            await self.initialize()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            yield conn

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        async with self.get_connection() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch_many(self, query: str, *args: Any) -> List[asyncpg.Record]:
        async with self.get_connection() as conn:
            return await conn.fetch(query, *args)

    async def fetch_val(self, query: str, *args: Any) -> Any:
        async with self.get_connection() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        async with self.get_connection() as conn:
            return await conn.execute(query, *args)

    async def health_check(self) -> bool:
        try:
            return await self.fetch_val("SELECT 1") == 1
        except Exception as e:
            logger.error("health_check: %s", e)
            return False

    async def get_projects(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        q = """
        SELECT project_id, project_name, project_type, description, status,
               created_at, updated_at
        FROM main.project
        ORDER BY project_id DESC
        LIMIT $1 OFFSET $2
        """
        rows = await self.fetch_many(q, limit, offset)
        return [_json_safe(dict(r)) for r in rows]

    async def get_project_by_id(self, project_id: int) -> Optional[Dict[str, Any]]:
        q = """
        SELECT project_id, project_name, project_type, description, status,
               created_at, updated_at
        FROM main.project WHERE project_id = $1
        """
        row = await self.fetch_one(q, project_id)
        return _json_safe(dict(row)) if row else None

    async def insert_project(
        self,
        project_name: str,
        project_type: Optional[str],
        description: Optional[str],
        status: Optional[str],
        created_by: str = "dashboard",
    ) -> Dict[str, Any]:
        q = """
        INSERT INTO main.project (project_name, project_type, description, status, created_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING project_id, project_name, project_type, description, status, created_at, updated_at
        """
        row = await self.fetch_one(q, project_name, project_type, description, status, created_by)
        return _json_safe(dict(row)) if row else {}

    async def get_workflow_runs(
        self, project_id: Optional[int] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if project_id is not None:
            q = """
            SELECT workflow_run_id, workflow_name, project_id, agent_instance_id, status,
                   input_data, result_data, started_at, finished_at, created_at, updated_at
            FROM main.workflow_run
            WHERE project_id = $1
            ORDER BY workflow_run_id DESC
            LIMIT $2
            """
            rows = await self.fetch_many(q, project_id, limit)
        else:
            q = """
            SELECT workflow_run_id, workflow_name, project_id, agent_instance_id, status,
                   input_data, result_data, started_at, finished_at, created_at, updated_at
            FROM main.workflow_run
            ORDER BY workflow_run_id DESC
            LIMIT $1
            """
            rows = await self.fetch_many(q, limit)
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            for k in ("input_data", "result_data"):
                if d.get(k) is not None and not isinstance(d[k], (dict, list)):
                    pass
            out.append(_json_safe(d))
        return out

    async def get_tasks_by_project(self, project_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        q = """
        SELECT task_id, project_id, agent_id, document_id, task_name, task_type,
               description, parameters, status, priority, task_notes, task_data,
               created_at, updated_at
        FROM main.task
        WHERE project_id = $1
        ORDER BY COALESCE(priority, 99), task_id
        LIMIT $2
        """
        rows = await self.fetch_many(q, project_id, limit)
        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("parameters"), str):
                try:
                    d["parameters"] = json.loads(d["parameters"])
                except Exception:
                    pass
            if isinstance(d.get("task_data"), str):
                try:
                    d["task_data"] = json.loads(d["task_data"])
                except Exception:
                    pass
            out.append(_json_safe(d))
        return out

    async def get_documents_by_project(self, project_id: int) -> List[Dict[str, Any]]:
        q = """
        SELECT document_id, project_id, document_name, document_type, raw_text_content,
               file_extension, file_mime_type, file_size_bytes,
               version_number, is_active_version, serialization_status,
               created_at, updated_at
        FROM main.project_document
        WHERE project_id = $1
        ORDER BY document_id DESC
        """
        rows = await self.fetch_many(q, project_id)
        out = []
        for r in rows:
            d = dict(r)
            # omit huge text in list view
            if d.get("raw_text_content"):
                d["raw_text_preview"] = (d["raw_text_content"][:200] + "…") if len(d["raw_text_content"]) > 200 else d["raw_text_content"]
                del d["raw_text_content"]
            out.append(_json_safe(d))
        return out

    async def insert_document_upload(
        self,
        project_id: int,
        document_name: str,
        document_type: str,
        raw_text: Optional[str],
        ext: Optional[str],
        mime: Optional[str],
        size: int,
        file_bytes: Optional[bytes],
    ) -> Dict[str, Any]:
        q = """
        INSERT INTO main.project_document (
            project_id, document_name, document_type, raw_text_content,
            file_extension, file_mime_type, file_size_bytes, file_content,
            version_number, is_active_version, created_by, serialization_status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, true, 'dashboard', 'PENDING')
        RETURNING document_id, project_id, document_name, document_type, file_extension,
                  file_size_bytes, serialization_status, created_at
        """
        row = await self.fetch_one(
            q,
            project_id,
            document_name,
            document_type,
            raw_text,
            ext,
            mime,
            size,
            file_bytes,
        )
        return _json_safe(dict(row)) if row else {}

    async def delete_document_if_pending(self, project_id: int, document_id: int) -> bool:
        q = """
        DELETE FROM main.project_document
        WHERE document_id = $1 AND project_id = $2
          AND COALESCE(serialization_status, 'PENDING') = 'PENDING'
        """
        status = await self.execute(q, document_id, project_id)
        return status.endswith("DELETE 1")

    async def dashboard_stats(self) -> Dict[str, Any]:
        projects = await self.fetch_val("SELECT COUNT(*) FROM main.project")
        tasks = await self.fetch_val("SELECT COUNT(*) FROM main.task")
        runs = await self.fetch_val(
            "SELECT COUNT(*) FROM main.workflow_run WHERE COALESCE(status,'') IN ('RUNNING','running')"
        )
        recent = await self.fetch_many(
            """
            SELECT workflow_run_id, workflow_name, project_id, status, started_at
            FROM main.workflow_run
            ORDER BY workflow_run_id DESC
            LIMIT 5
            """
        )
        return {
            "project_count": int(projects or 0),
            "task_count": int(tasks or 0),
            "active_workflow_count": int(runs or 0),
            "recent_workflow_runs": [_json_safe(dict(r)) for r in recent],
        }

    async def get_workflow_run_by_id(self, workflow_run_id: int) -> Optional[Dict[str, Any]]:
        q = """
        SELECT workflow_run_id, workflow_name, project_id, agent_instance_id, status,
               input_data, result_data, started_at, finished_at, created_at, updated_at
        FROM main.workflow_run WHERE workflow_run_id = $1
        """
        row = await self.fetch_one(q, workflow_run_id)
        if not row:
            return None
        d = dict(row)
        for k in ("input_data", "result_data"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    pass
        return _json_safe(d)


db_manager = DatabaseManager()


async def get_db() -> DatabaseManager:
    return db_manager
