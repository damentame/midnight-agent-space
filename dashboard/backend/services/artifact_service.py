from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from .jsonb_utils import decode_jsonb_fields, jsonb_dumps
from .schema_support import schema_support


class ArtifactService:
    _JSON_FIELDS = ("metadata",)

    async def record_artifact(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        project_id: int,
        artifact_type: str,
        artifact_name: str,
        artifact_path: Optional[str],
        content_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not await schema_support.table_exists(db, "agent_artifact"):
            return {}
        row = await db.fetch_one(
            """
            INSERT INTO main.agent_artifact (
                agent_run_id,
                project_id,
                artifact_type,
                artifact_name,
                artifact_path,
                content_type,
                size_bytes,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            run_id,
            project_id,
            artifact_type,
            artifact_name,
            artifact_path,
            content_type,
            size_bytes,
            jsonb_dumps(metadata or {}),
        )
        return decode_jsonb_fields(dict(row), self._JSON_FIELDS) if row else {}

    async def list_artifacts(
        self,
        db: DatabaseManager,
        *,
        run_id: int,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "agent_artifact"):
            return []
        rows = await db.fetch_many(
            """
            SELECT *
            FROM main.agent_artifact
            WHERE agent_run_id = $1
            ORDER BY agent_artifact_id DESC
            LIMIT $2
            """,
            run_id,
            limit,
        )
        return [decode_jsonb_fields(dict(row), self._JSON_FIELDS) for row in rows]


artifact_service = ArtifactService()
