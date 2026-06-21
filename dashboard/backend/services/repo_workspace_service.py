"""Create project workspace folders and initialize git repositories."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .git_worktree_service import git_worktree_service


def slugify_project_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip()).strip("-").lower()
    return slug or "project"


def default_projects_parent() -> Path:
    documents = Path.home() / "Documents" / "Midnight" / "projects"
    documents.mkdir(parents=True, exist_ok=True)
    return documents.resolve()


class RepoWorkspaceService:
    def resolve_unique_dir(self, parent: Path, folder_name: str) -> Path:
        parent = parent.resolve()
        candidate = parent / folder_name
        if not candidate.exists():
            return candidate
        index = 2
        while True:
            next_path = parent / f"{folder_name}-{index}"
            if not next_path.exists():
                return next_path
            index += 1

    def _run_git(self, argv: list[str], *, cwd: Path) -> Dict[str, Any]:
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            return {
                "ok": completed.returncode == 0,
                "stdout": (completed.stdout or "").strip(),
                "stderr": (completed.stderr or "").strip(),
                "exit_code": completed.returncode,
            }
        except Exception as exc:
            return {"ok": False, "stderr": str(exc), "exit_code": -1}

    async def init_git_repository(self, repo_path: Path) -> Dict[str, Any]:
        repo_path = repo_path.resolve()
        if not repo_path.exists():
            return {"ok": False, "error": f"path does not exist: {repo_path}"}

        valid = await git_worktree_service.validate_repository(str(repo_path))
        if valid.get("ok"):
            return {
                "ok": True,
                "initialized": False,
                "repo_path": str(valid.get("repo_path") or repo_path),
                "message": "Already a git repository",
            }

        init_result = self._run_git(["git", "init"], cwd=repo_path)
        if not init_result.get("ok"):
            return {
                "ok": False,
                "error": init_result.get("stderr") or "git init failed",
                "initialized": False,
            }

        gitignore = repo_path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "node_modules/\n.dist/\ndist/\nbuild/\n.env\n.venv/\n__pycache__/\n.midnight/\n",
                encoding="utf-8",
            )

        valid_after = await git_worktree_service.validate_repository(str(repo_path))
        if valid_after.get("ok"):
            try:
                await git_worktree_service.resolve_base_branch(str(repo_path), "main")
            except RuntimeError as exc:
                return {
                    "ok": False,
                    "initialized": True,
                    "repo_path": str(valid_after.get("repo_path") or repo_path),
                    "error": str(exc),
                }

        return {
            "ok": bool(valid_after.get("ok")),
            "initialized": True,
            "repo_path": str(valid_after.get("repo_path") or repo_path),
            "stderr": valid_after.get("stderr"),
            "message": "Git repository initialized",
        }

    async def create_project_workspace(
        self,
        *,
        parent_path: str,
        project_name: str,
    ) -> Dict[str, Any]:
        parent = Path(parent_path).expanduser().resolve()
        if not parent.exists() or not parent.is_dir():
            return {"ok": False, "error": f"parent folder does not exist: {parent}"}

        folder_name = slugify_project_name(project_name)
        target = self.resolve_unique_dir(parent, folder_name)
        target.mkdir(parents=True, exist_ok=False)

        init = await self.init_git_repository(target)
        if not init.get("ok"):
            return {
                "ok": False,
                "error": init.get("error") or "failed to initialize git repository",
                "repo_path": str(target),
                "created": True,
            }

        return {
            "ok": True,
            "created": True,
            "initialized": True,
            "folder_name": target.name,
            "repo_path": init.get("repo_path") or str(target),
            "parent_path": str(parent),
        }

    async def prepare_workspace(
        self,
        *,
        parent_path: Optional[str],
        project_name: str,
        mode: str = "create",
        existing_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        mode:
          - create: mkdir {parent}/{slug} and git init
          - init_here: git init in existing_path
          - use_existing: validate existing git repo at existing_path
        """
        if mode == "use_existing":
            if not existing_path:
                return {"ok": False, "error": "existing_path is required"}
            valid = await git_worktree_service.validate_repository(existing_path)
            if not valid.get("ok"):
                return {"ok": False, "error": valid.get("error") or "not a git repository"}
            return {
                "ok": True,
                "created": False,
                "initialized": False,
                "repo_path": str(valid.get("repo_path") or existing_path),
            }

        if mode == "init_here":
            if not existing_path:
                return {"ok": False, "error": "existing_path is required"}
            init = await self.init_git_repository(Path(existing_path))
            return {
                "ok": bool(init.get("ok")),
                "created": False,
                "initialized": bool(init.get("initialized")),
                "repo_path": init.get("repo_path") or existing_path,
                "error": init.get("error"),
                "message": init.get("message"),
            }

        parent = parent_path or str(default_projects_parent())
        return await self.create_project_workspace(parent_path=parent, project_name=project_name)


repo_workspace_service = RepoWorkspaceService()
