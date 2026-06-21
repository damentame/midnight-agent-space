"""Scan a git repository and ingest text files as RAG-ready project documents."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..database import DatabaseManager
from ..services.git_worktree_service import git_worktree_service
from ..services.jsonb_utils import jsonb_dumps

logger = logging.getLogger(__name__)

IGNORE_DIR_NAMES = {
    ".git",
    ".midnight",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "out",
    "target",
    ".next",
    ".turbo",
    "coverage",
    ".idea",
    ".vscode",
    "vendor",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".rb",
    ".php",
    ".swift",
    ".toml",
    ".ini",
    ".cfg",
    ".env.example",
    ".vue",
    ".svelte",
}

MAX_FILE_BYTES = 256 * 1024
MAX_FILES_DEFAULT = 400
PREVIEW_CHARS = 1600


@dataclass
class CodebaseJobState:
    project_id: int
    status: str = "idle"
    phase: str = "idle"
    message: str = ""
    current: int = 0
    total: int = 0
    files_seen: int = 0
    files_imported: int = 0
    files_skipped: int = 0
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class CodebaseSerializationService:
    def __init__(self) -> None:
        self._jobs: Dict[int, CodebaseJobState] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def get_job(self, project_id: int) -> Optional[CodebaseJobState]:
        return self._jobs.get(project_id)

    def _lock_for(self, project_id: int) -> asyncio.Lock:
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]

    def _should_skip_dir(self, name: str) -> bool:
        return name in IGNORE_DIR_NAMES or name.startswith(".")

    def _is_text_candidate(self, path: Path) -> bool:
        if not path.is_file():
            return False
        ext = path.suffix.lower()
        if ext in TEXT_EXTENSIONS:
            return True
        mime, _ = mimetypes.guess_type(str(path))
        return bool(mime and mime.startswith("text/"))

    def discover_files(self, repo_root: Path, *, max_files: int) -> List[Path]:
        files: List[Path] = []
        stack: List[Path] = [repo_root]
        while stack and len(files) < max_files:
            current = stack.pop()
            try:
                children = sorted(current.iterdir(), key=lambda p: p.name.lower())
            except (OSError, PermissionError):
                continue
            for child in reversed(children):
                if child.is_dir():
                    if not self._should_skip_dir(child.name):
                        stack.append(child)
                elif self._is_text_candidate(child):
                    try:
                        if child.stat().st_size <= MAX_FILE_BYTES:
                            files.append(child)
                    except OSError:
                        continue
        return sorted(files, key=lambda p: str(p.relative_to(repo_root)).lower())

    async def _delete_existing_codebase_documents(self, db: DatabaseManager, project_id: int) -> int:
        row = await db.fetch_one(
            """
            WITH deleted AS (
                DELETE FROM main.project_document
                WHERE project_id = $1 AND document_type = 'codebase_file'
                RETURNING document_id
            )
            SELECT COUNT(*)::int AS count FROM deleted
            """,
            project_id,
        )
        return int((row or {}).get("count") or 0)

    async def _import_file(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        repo_root: Path,
        file_path: Path,
    ) -> bool:
        rel = str(file_path.relative_to(repo_root)).replace("\\", "/")
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

        ext = file_path.suffix.lower() or ".txt"
        mime = mimetypes.guess_type(str(file_path))[0] or "text/plain"
        preview = raw[:PREVIEW_CHARS]
        descriptor = {
            "rag_ready": True,
            "content_kind": "text",
            "source_file": {
                "name": rel,
                "extension": ext,
                "mime_type": mime,
                "size_bytes": len(raw.encode("utf-8")),
                "relative_path": rel,
            },
            "agent_context": {
                "summary": f"Codebase file {rel} ingested for project context.",
                "text_preview": preview,
                "extraction_status": "codebase_ingested",
                "relative_path": rel,
            },
            "retrieval": {
                "namespace": "codebase_file",
                "modalities": ["text"],
                "keywords": [rel, ext.lstrip("."), "codebase"],
            },
        }

        row = await db.insert_document_upload(
            project_id=project_id,
            document_name=rel[:255],
            document_type="codebase_file",
            raw_text=raw,
            ext=ext,
            mime=mime,
            size=len(raw.encode("utf-8")),
            file_bytes=None,
        )
        document_id = int(row.get("document_id") or 0)
        if document_id <= 0:
            return False

        await db.execute(
            """
            UPDATE main.project_document
            SET structured_json = $1::jsonb,
                serialized_payload = $1::jsonb,
                serialization_status = 'RAG_READY',
                embedding_status = 'READY_FOR_EMBEDDING',
                chunk_count = GREATEST(1, CEIL(LENGTH(COALESCE(raw_text_content, '')) / 1200.0)::integer),
                updated_at = NOW()
            WHERE project_id = $2 AND document_id = $3
            """,
            jsonb_dumps(descriptor),
            project_id,
            document_id,
        )
        return True

    async def run_job(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        repo_path: str,
        max_files: int = MAX_FILES_DEFAULT,
    ) -> None:
        job = self._jobs.setdefault(project_id, CodebaseJobState(project_id=project_id))
        job.status = "running"
        job.phase = "validating"
        job.message = "Validating repository…"
        job.current = 0
        job.total = 0
        job.error = None
        job.result = None

        try:
            valid = await git_worktree_service.validate_repository(repo_path)
            if not valid.get("ok"):
                raise ValueError(valid.get("error") or "Path is not a git repository")

            repo_root = Path(str(valid.get("repo_path") or repo_path)).resolve()

            job.phase = "scanning"
            job.message = "Scanning repository files…"
            files = await asyncio.to_thread(self.discover_files, repo_root, max_files=max_files)
            job.files_seen = len(files)
            job.total = len(files)
            job.phase = "importing"
            job.message = f"Importing {len(files)} files into project context…"

            removed = await self._delete_existing_codebase_documents(db, project_id)
            imported = 0
            skipped = 0

            for index, file_path in enumerate(files, start=1):
                job.current = index
                job.message = f"Importing {file_path.relative_to(repo_root)} ({index}/{len(files)})"
                ok = await self._import_file(db, project_id=project_id, repo_root=repo_root, file_path=file_path)
                if ok:
                    imported += 1
                else:
                    skipped += 1
                job.files_imported = imported
                job.files_skipped = skipped

                if index % 25 == 0:
                    await asyncio.sleep(0)

            job.phase = "done"
            job.status = "completed"
            job.message = f"Imported {imported} codebase files ({skipped} skipped)."
            job.result = {
                "ok": True,
                "repo_path": str(repo_root),
                "files_discovered": len(files),
                "files_imported": imported,
                "files_skipped": skipped,
                "previous_codebase_documents_removed": removed,
            }
        except Exception as exc:
            logger.exception("codebase serialization failed project_id=%s", project_id)
            job.status = "failed"
            job.phase = "failed"
            job.error = str(exc)
            job.message = str(exc)
            job.result = {"ok": False, "error": str(exc)}

    async def start(
        self,
        db: DatabaseManager,
        *,
        project_id: int,
        repo_path: str,
        max_files: int = MAX_FILES_DEFAULT,
    ) -> Dict[str, Any]:
        lock = self._lock_for(project_id)
        if lock.locked():
            job = self._jobs.get(project_id)
            return {
                "ok": False,
                "error": "Codebase serialization already running for this project",
                "status": job.status if job else "running",
            }

        async def _runner() -> None:
            async with lock:
                await self.run_job(db, project_id=project_id, repo_path=repo_path, max_files=max_files)

        self._jobs[project_id] = CodebaseJobState(
            project_id=project_id,
            status="queued",
            phase="queued",
            message="Queued…",
        )
        asyncio.create_task(_runner())
        return {"ok": True, "status": "queued", "message": "Codebase serialization started"}

    def status_payload(self, project_id: int) -> Dict[str, Any]:
        job = self._jobs.get(project_id)
        if not job:
            return {"status": "idle", "phase": "idle", "message": "No codebase serialization in progress"}
        percent = int((job.current / job.total) * 100) if job.total > 0 else 0
        return {
            "status": job.status,
            "phase": job.phase,
            "message": job.message,
            "current": job.current,
            "total": job.total,
            "percent": percent,
            "files_seen": job.files_seen,
            "files_imported": job.files_imported,
            "files_skipped": job.files_skipped,
            "error": job.error,
            "result": job.result,
            "long_running": job.total > 80 or job.status == "running",
        }


codebase_serialization_service = CodebaseSerializationService()
