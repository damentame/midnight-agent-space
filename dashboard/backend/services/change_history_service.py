from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from .jsonb_utils import decode_jsonb_fields, jsonb_dumps
from .schema_support import schema_support


class ChangeHistoryService:
    _JSON_FIELDS = ("payload",)

    async def list_changes(
        self,
        db: DatabaseManager,
        project_id: int,
        limit: int = 100,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where_clauses = ["project_id = $1"]
        params: List[Any] = [project_id]
        next_param_index = 2
        if entity_type is not None:
            where_clauses.append(f"entity_type = ${next_param_index}")
            params.append(entity_type)
            next_param_index += 1
        if entity_id is not None:
            where_clauses.append(f"entity_id = ${next_param_index}")
            params.append(entity_id)
            next_param_index += 1
        where_sql = " AND ".join(where_clauses)
        limit_param = f"${next_param_index}"
        params.append(limit)

        if await schema_support.table_exists(db, "change_history"):
            rows = await db.fetch_many(
                f"""
                SELECT
                    change_history_id,
                    project_id,
                    entity_type,
                    entity_id,
                    source,
                    change_type,
                    title,
                    summary,
                    payload,
                    created_by,
                    created_at
                FROM main.change_history
                WHERE {where_sql}
                ORDER BY change_history_id DESC
                LIMIT {limit_param}
                """,
                *params,
            )
            return [decode_jsonb_fields(dict(r), self._JSON_FIELDS) for r in rows]

        # Fallback to legacy event_log for compatibility when migration is not applied.
        if await schema_support.table_exists(db, "event_log"):
            rows = await db.fetch_many(
                f"""
                SELECT
                    event_log_id AS change_history_id,
                    project_id,
                    entity_type,
                    entity_id,
                    'event_log'::text AS source,
                    event_type AS change_type,
                    event_type AS title,
                    NULL::text AS summary,
                    payload,
                    created_by,
                    created_at
                FROM main.event_log
                WHERE {where_sql}
                ORDER BY event_log_id DESC
                LIMIT {limit_param}
                """,
                *params,
            )
            return [decode_jsonb_fields(dict(r), self._JSON_FIELDS) for r in rows]

        return []

    async def record_change(
        self,
        db: DatabaseManager,
        project_id: int,
        entity_type: str,
        entity_id: Optional[int],
        source: str,
        change_type: str,
        title: str,
        summary: Optional[str],
        payload: Optional[Dict[str, Any]],
        created_by: str = "dashboard",
    ) -> None:
        if await schema_support.table_exists(db, "change_history"):
            await db.execute(
                """
                INSERT INTO main.change_history (
                    project_id,
                    entity_type,
                    entity_id,
                    source,
                    change_type,
                    title,
                    summary,
                    payload,
                    created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                project_id,
                entity_type,
                entity_id,
                source,
                change_type,
                title,
                summary,
                jsonb_dumps(payload),
                created_by,
            )
            return

        # Keep compatibility by writing legacy events if new table is unavailable.
        if await schema_support.table_exists(db, "event_log"):
            await db.execute(
                """
                INSERT INTO main.event_log (
                    entity_type,
                    entity_id,
                    project_id,
                    event_type,
                    payload,
                    created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                entity_type,
                entity_id,
                project_id,
                change_type,
                jsonb_dumps(payload),
                created_by,
            )


change_history_service = ChangeHistoryService()
