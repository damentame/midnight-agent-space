from __future__ import annotations

from typing import Any, Dict, Optional

from ..database import DatabaseManager
from .jsonb_utils import decode_jsonb_fields, jsonb_dumps
from .schema_support import schema_support


class ProjectMetadataService:
    _JSON_FIELDS = ("metadata", "runtime_preferences")

    async def get_project_metadata(self, db: DatabaseManager, project_id: int) -> Dict[str, Any]:
        project = await db.get_project_by_id(project_id)
        if not project:
            return {}

        has_metadata = await schema_support.column_exists(db, "project", "metadata")
        has_repository_url = await schema_support.column_exists(db, "project", "repository_url")
        has_default_branch = await schema_support.column_exists(db, "project", "default_branch")
        has_runtime_preferences = await schema_support.column_exists(
            db, "project", "runtime_preferences"
        )

        if not (has_metadata or has_repository_url or has_default_branch or has_runtime_preferences):
            return {
                "project_id": project_id,
                "metadata": {},
                "repository_url": None,
                "default_branch": None,
                "runtime_preferences": {},
                "schema_ready": False,
            }

        select_parts = ["project_id"]
        select_parts.append("COALESCE(metadata, '{}'::jsonb) AS metadata" if has_metadata else "'{}'::jsonb AS metadata")
        select_parts.append("repository_url" if has_repository_url else "NULL::text AS repository_url")
        select_parts.append("default_branch" if has_default_branch else "NULL::text AS default_branch")
        select_parts.append(
            "COALESCE(runtime_preferences, '{}'::jsonb) AS runtime_preferences"
            if has_runtime_preferences
            else "'{}'::jsonb AS runtime_preferences"
        )
        row = await db.fetch_one(
            f"""
            SELECT {", ".join(select_parts)}
            FROM main.project
            WHERE project_id = $1
            """,
            project_id,
        )
        if not row:
            return {}

        data = decode_jsonb_fields(dict(row), self._JSON_FIELDS)
        data["schema_ready"] = True
        return data

    async def update_project_metadata(
        self,
        db: DatabaseManager,
        project_id: int,
        metadata: Optional[Dict[str, Any]],
        repository_url: Optional[str],
        default_branch: Optional[str],
        runtime_preferences: Optional[Dict[str, Any]],
        updated_by: str = "dashboard",
    ) -> Dict[str, Any]:
        exists = await db.get_project_by_id(project_id)
        if not exists:
            return {}

        has_metadata = await schema_support.column_exists(db, "project", "metadata")
        has_repository_url = await schema_support.column_exists(db, "project", "repository_url")
        has_default_branch = await schema_support.column_exists(db, "project", "default_branch")
        has_runtime_preferences = await schema_support.column_exists(
            db, "project", "runtime_preferences"
        )
        if not (has_metadata or has_repository_url or has_default_branch or has_runtime_preferences):
            return await self.get_project_metadata(db, project_id)

        assignments = []
        values = []
        arg_pos = 1
        if has_metadata and metadata is not None:
            assignments.append(f"metadata = ${arg_pos}")
            values.append(jsonb_dumps(metadata))
            arg_pos += 1
        if has_repository_url and repository_url is not None:
            assignments.append(f"repository_url = ${arg_pos}")
            values.append(repository_url)
            arg_pos += 1
        if has_default_branch and default_branch is not None:
            assignments.append(f"default_branch = ${arg_pos}")
            values.append(default_branch)
            arg_pos += 1
        if has_runtime_preferences and runtime_preferences is not None:
            assignments.append(f"runtime_preferences = ${arg_pos}")
            values.append(jsonb_dumps(runtime_preferences))
            arg_pos += 1

        assignments.append(f"updated_by = ${arg_pos}")
        values.append(updated_by)
        arg_pos += 1
        assignments.append("updated_at = NOW()")
        values.append(project_id)

        await db.execute(
            f"""
            UPDATE main.project
            SET {", ".join(assignments)}
            WHERE project_id = ${arg_pos}
            """,
            *values,
        )
        return await self.get_project_metadata(db, project_id)


project_metadata_service = ProjectMetadataService()
