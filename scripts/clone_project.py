#!/usr/bin/env python3
"""Clone a MAS project including documents (with binaries) for testing."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.backend.database import db_manager
from dashboard.backend.services.project_metadata_service import project_metadata_service


async def clone_project(source_id: int, new_name: str) -> int:
    await db_manager.initialize()
    try:
        source = await db_manager.get_project_by_id(source_id)
        if not source:
            raise SystemExit(f"Source project {source_id} not found")

        created = await db_manager.insert_project(
            project_name=new_name,
            project_type=source.get("project_type"),
            description=source.get("description"),
            status=source.get("status") or "active",
            created_by="clone-script",
        )
        new_id = int(created.get("project_id") or 0)
        if new_id <= 0:
            raise SystemExit("Failed to create target project")

        meta = await project_metadata_service.get_project_metadata(db_manager, source_id)
        await project_metadata_service.update_project_metadata(
            db_manager,
            new_id,
            metadata=meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {},
            repository_url=meta.get("repository_url"),
            default_branch=meta.get("default_branch"),
            runtime_preferences=meta.get("runtime_preferences")
            if isinstance(meta.get("runtime_preferences"), dict)
            else {},
            updated_by="clone-script",
        )

        docs = await db_manager.get_documents_by_project(source_id)
        id_map: dict[int, int] = {}
        pending_parent: list[tuple[int, int | None]] = []

        for doc in sorted(docs, key=lambda d: int(d.get("document_id") or 0)):
            if not doc.get("is_active_version", True):
                continue
            old_id = int(doc.get("document_id") or 0)
            file_row = await db_manager.get_document_file(source_id, old_id)
            file_bytes = None
            if file_row and file_row.get("file_content") is not None:
                content = file_row["file_content"]
                file_bytes = content.tobytes() if hasattr(content, "tobytes") else content

            structured = doc.get("structured_json")
            if isinstance(structured, str):
                try:
                    structured = json.loads(structured)
                except Exception:
                    structured = None

            row = await db_manager.insert_document_upload(
                project_id=new_id,
                document_name=str(doc.get("document_name") or "document")[:255],
                document_type=str(doc.get("document_type") or "text"),
                raw_text=doc.get("raw_text_content"),
                ext=doc.get("file_extension") or ".txt",
                mime=doc.get("mime_type") or "text/plain",
                size=int(doc.get("file_size") or 0),
                file_bytes=file_bytes,
                parent_document_id=None,
                structured_json=structured if isinstance(structured, dict) else None,
            )
            new_doc_id = int(row.get("document_id") or 0)
            id_map[old_id] = new_doc_id
            pending_parent.append((new_doc_id, doc.get("parent_document_id")))

            await db_manager.execute(
                """
                UPDATE main.project_document
                SET serialization_status = COALESCE($3, serialization_status),
                    embedding_status = COALESCE($4, embedding_status),
                    updated_at = NOW()
                WHERE project_id = $1 AND document_id = $2
                """,
                new_id,
                new_doc_id,
                doc.get("serialization_status"),
                doc.get("embedding_status"),
            )

        for new_doc_id, old_parent in pending_parent:
            if old_parent is None:
                continue
            mapped = id_map.get(int(old_parent))
            if mapped:
                await db_manager.execute(
                    """
                    UPDATE main.project_document
                    SET parent_document_id = $3, updated_at = NOW()
                    WHERE project_id = $1 AND document_id = $2
                    """,
                    new_id,
                    new_doc_id,
                    mapped,
                )

        # Refresh figma_source document_id references in metadata
        meta_new = await project_metadata_service.get_project_metadata(db_manager, new_id)
        metadata = meta_new.get("metadata") or {}
        if isinstance(metadata, dict):
            figma_source = metadata.get("figma_source")
            if isinstance(figma_source, dict) and figma_source.get("document_id"):
                old = int(figma_source["document_id"])
                if old in id_map:
                    figma_source["document_id"] = id_map[old]
                    figma_source["active_document_id"] = id_map[old]
                    metadata["figma_source"] = figma_source
                    await project_metadata_service.update_project_metadata(
                        db_manager,
                        new_id,
                        metadata=metadata,
                        updated_by="clone-script",
                    )

        print(json.dumps({"ok": True, "source_project_id": source_id, "new_project_id": new_id, "new_name": new_name, "documents_copied": len(id_map)}))
        return new_id
    finally:
        await db_manager.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone a MAS project")
    parser.add_argument("source_id", type=int)
    parser.add_argument("new_name", type=str)
    args = parser.parse_args()
    asyncio.run(clone_project(args.source_id, args.new_name))


if __name__ == "__main__":
    main()
