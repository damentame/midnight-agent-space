from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .verification_service import CommandExecutionResult, verification_service


@dataclass
class WorktreePlan:
    branch_name: str
    worktree_path: str
    create_commands: List[List[str]]
    reuse_existing_branch: bool = False


class GitWorktreeService:
    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower() or "run"

    async def _run(
        self,
        argv: List[str],
        *,
        cwd: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> CommandExecutionResult:
        return await verification_service.run_command(
            argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )

    async def validate_repository(self, repo_path: str) -> Dict[str, Any]:
        root = Path(repo_path).resolve()
        if not root.exists():
            return {"ok": False, "error": f"repository path does not exist: {root}"}
        if not (root / ".git").exists():
            # Worktrees may not have a local .git dir; rev-parse is the source of truth.
            pass
        result = await self._run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"])
        if not result.ok:
            return {
                "ok": False,
                "error": "path is not a git repository",
                "stderr": result.stderr.strip(),
            }
        top_level = await self._run(["git", "-C", str(root), "rev-parse", "--show-toplevel"])
        return {
            "ok": top_level.ok,
            "repo_path": (top_level.stdout.strip() or str(root)),
            "stderr": top_level.stderr.strip(),
        }

    async def list_worktrees(self, repo_path: str) -> List[Dict[str, Any]]:
        result = await self._run(["git", "-C", repo_path, "worktree", "list", "--porcelain"])
        if not result.ok:
            return []
        rows: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}
        for line in result.stdout.splitlines():
            if not line.strip():
                if current:
                    rows.append(current)
                    current = {}
                continue
            if line.startswith("worktree "):
                current["worktree_path"] = line.replace("worktree ", "", 1).strip()
            elif line.startswith("HEAD "):
                current["head"] = line.replace("HEAD ", "", 1).strip()
            elif line.startswith("branch "):
                current["branch"] = line.replace("branch ", "", 1).replace("refs/heads/", "").strip()
            else:
                current.setdefault("flags", []).append(line.strip())
        if current:
            rows.append(current)
        return rows

    async def create_worktree(
        self,
        repo_path: str,
        project_id: int,
        run_id: int,
        base_branch: str = "main",
        prefix: str = "mas/quick-run",
        create_branch: bool = True,
        worktree_base_path: Optional[str] = None,
    ) -> WorktreePlan:
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            raise RuntimeError(valid.get("error") or "invalid repository")
        canonical_repo_path = str(valid.get("repo_path") or repo_path)

        branch_name = f"{self._slug(prefix)}/{run_id}"
        worktree_path = self.resolve_worktree_path(
            repo_path=canonical_repo_path,
            project_id=project_id,
            run_id=run_id,
            worktree_base_path=worktree_base_path,
        )
        Path(worktree_path).parent.mkdir(parents=True, exist_ok=True)

        existing = await self.list_worktrees(canonical_repo_path)
        for row in existing:
            if row.get("worktree_path") == worktree_path:
                return WorktreePlan(
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    create_commands=[],
                    reuse_existing_branch=True,
                )

        branch_exists = await self._run(
            ["git", "-C", canonical_repo_path, "show-ref", "--verify", f"refs/heads/{branch_name}"]
        )
        reuse_existing_branch = branch_exists.ok

        create_commands: List[List[str]] = []
        if create_branch and not reuse_existing_branch:
            create_commands.append(
                [
                    "git",
                    "-C",
                    canonical_repo_path,
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    worktree_path,
                    base_branch,
                ]
            )
        else:
            # Branch already exists (or branch creation disabled): attach worktree to that branch.
            target_ref = branch_name if reuse_existing_branch else base_branch
            create_commands.append(
                ["git", "-C", canonical_repo_path, "worktree", "add", worktree_path, target_ref]
            )

        for command in create_commands:
            result = await self._run(command, timeout_seconds=60)
            if not result.ok:
                raise RuntimeError(
                    f"failed to create worktree: {' '.join(command)} :: {result.stderr.strip()}"
                )

        return WorktreePlan(
            branch_name=branch_name,
            worktree_path=worktree_path,
            create_commands=create_commands,
            reuse_existing_branch=reuse_existing_branch,
        )

    def resolve_worktree_path(
        self,
        *,
        repo_path: str,
        project_id: int,
        run_id: int,
        worktree_base_path: Optional[str] = None,
    ) -> str:
        repo_root = Path(repo_path).resolve()
        if worktree_base_path:
            base = Path(worktree_base_path).expanduser()
            if not base.is_absolute():
                base = (repo_root / base).resolve()
        else:
            base = repo_root / ".midnight" / "worktrees"
        return str(base / str(project_id) / str(run_id))

    async def capture_diff(self, worktree_path: str, max_chars: int = 60000) -> Dict[str, Any]:
        status = await self._run(["git", "-C", worktree_path, "status", "--short"])
        diff_stat = await self._run(["git", "-C", worktree_path, "diff", "--stat"])
        diff_full = await self._run(["git", "-C", worktree_path, "diff", "--"])
        return {
            "ok": status.ok and diff_full.ok,
            "status_lines": [line for line in status.stdout.splitlines() if line.strip()],
            "diff_stat": diff_stat.stdout.strip(),
            "diff_excerpt": diff_full.stdout[:max_chars],
            "stderr": "\n".join(
                [text for text in [status.stderr.strip(), diff_stat.stderr.strip(), diff_full.stderr.strip()] if text]
            ),
        }

    async def commit_changes(
        self,
        *,
        worktree_path: str,
        message: str,
        author_name: str = "MAS Dashboard",
        author_email: str = "dashboard@local",
    ) -> Dict[str, Any]:
        status = await self._run(["git", "-C", worktree_path, "status", "--porcelain"])
        changed = [line for line in status.stdout.splitlines() if line.strip()]
        if not changed:
            return {"ok": True, "committed": False, "reason": "no changes"}

        add_result = await self._run(["git", "-C", worktree_path, "add", "--all"], timeout_seconds=60)
        if not add_result.ok:
            return {
                "ok": False,
                "committed": False,
                "error": add_result.stderr.strip() or "git add failed",
            }

        commit_result = await self._run(
            [
                "git",
                "-C",
                worktree_path,
                "-c",
                f"user.name={author_name}",
                "-c",
                f"user.email={author_email}",
                "commit",
                "-m",
                message,
            ],
            timeout_seconds=60,
        )
        if not commit_result.ok:
            return {
                "ok": False,
                "committed": False,
                "error": commit_result.stderr.strip() or "git commit failed",
            }

        rev_result = await self._run(["git", "-C", worktree_path, "rev-parse", "HEAD"])
        return {
            "ok": rev_result.ok,
            "committed": True,
            "commit_hash": rev_result.stdout.strip() if rev_result.ok else None,
            "stderr": rev_result.stderr.strip(),
        }


git_worktree_service = GitWorktreeService()
