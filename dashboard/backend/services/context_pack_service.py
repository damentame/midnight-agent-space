from __future__ import annotations

from typing import Any, Dict

from ..database import DatabaseManager
from .change_history_service import change_history_service
from .document_version_service import document_version_service
from .project_metadata_service import project_metadata_service


class ContextPackService:
    async def build_context_pack(
        self,
        db: DatabaseManager,
        project_id: int,
        include_change_history: bool = True,
        include_versions: bool = True,
        limit: int = 20,
    ) -> Dict[str, Any]:
        project = await db.get_project_by_id(project_id)
        if not project:
            return {}

        metadata = await project_metadata_service.get_project_metadata(db, project_id)
        documents = await db.get_documents_by_project(project_id)
        tasks = await db.get_tasks_by_project(project_id, limit=limit)

        document_versions: Dict[str, Any] = {}
        if include_versions:
            for d in documents[:limit]:
                document_id = d.get("document_id")
                if document_id is None:
                    continue
                versions = await document_version_service.list_versions(
                    db,
                    project_id=project_id,
                    document_id=int(document_id),
                    limit=5,
                )
                document_versions[str(document_id)] = versions

        history = []
        if include_change_history:
            history = await change_history_service.list_changes(
                db,
                project_id=project_id,
                limit=limit,
            )

        return {
            "project": project,
            "project_metadata": metadata,
            "documents": documents[:limit],
            "document_versions": document_versions,
            "tasks": tasks[:limit],
            "recent_changes": history[:limit],
        }


context_pack_service = ContextPackService()
