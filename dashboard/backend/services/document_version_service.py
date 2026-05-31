from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from .jsonb_utils import jsonb_dumps
from .schema_support import schema_support


class DocumentVersionService:
    async def list_versions(
        self,
        db: DatabaseManager,
        project_id: int,
        document_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "document_version"):
            return []

        rows = await db.fetch_many(
            """
            SELECT
                document_version_id,
                project_id,
                document_id,
                version_number,
                version_label,
                source,
                content_hash,
                change_summary,
                created_by,
                created_at
            FROM main.document_version
            WHERE project_id = $1
              AND document_id = $2
            ORDER BY version_number DESC
            LIMIT $3
            """,
            project_id,
            document_id,
            limit,
        )
        return [dict(r) for r in rows]

    async def create_version(
        self,
        db: DatabaseManager,
        project_id: int,
        document_id: int,
        version_label: Optional[str],
        source: Optional[str],
        change_summary: Optional[str],
        raw_text_content: Optional[str],
        structured_json: Optional[Dict[str, Any]],
        content_hash: Optional[str],
        created_by: str = "dashboard",
    ) -> Dict[str, Any]:
        if not await schema_support.table_exists(db, "document_version"):
            return {}

        current_max = await db.fetch_val(
            """
            SELECT COALESCE(MAX(version_number), 0)
            FROM main.document_version
            WHERE project_id = $1
              AND document_id = $2
            """,
            project_id,
            document_id,
        )
        next_version = int(current_max or 0) + 1
        row = await db.fetch_one(
            """
            INSERT INTO main.document_version (
                project_id,
                document_id,
                version_number,
                version_label,
                source,
                content_hash,
                change_summary,
                raw_text_content,
                structured_json,
                created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING
                document_version_id,
                project_id,
                document_id,
                version_number,
                version_label,
                source,
                content_hash,
                change_summary,
                created_by,
                created_at
            """,
            project_id,
            document_id,
            next_version,
            version_label,
            source,
            content_hash,
            change_summary,
            raw_text_content,
            jsonb_dumps(structured_json),
            created_by,
        )
        return dict(row) if row else {}


document_version_service = DocumentVersionService()
