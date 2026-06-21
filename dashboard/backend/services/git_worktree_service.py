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

    async def _branch_exists(self, repo_path: str, branch: str) -> bool:
        name = (branch or "").strip()
        if not name:
            return False
        result = await self._run(
            ["git", "-C", repo_path, "show-ref", "--verify", f"refs/heads/{name}"]
        )
        return result.ok

    async def _has_commits(self, repo_path: str) -> bool:
        result = await self._run(["git", "-C", repo_path, "rev-parse", "--verify", "HEAD"])
        return result.ok

    async def _create_initial_commit(self, repo_path: str, branch: str) -> None:
        branch_name = (branch or "main").strip() or "main"
        checkout = await self._run(["git", "-C", repo_path, "checkout", "-B", branch_name])
        if not checkout.ok:
            raise RuntimeError(
                checkout.stderr.strip() or f"failed to create branch {branch_name}"
            )
        await self._run(["git", "-C", repo_path, "add", "-A"], timeout_seconds=60)
        commit = await self._run(
            [
                "git",
                "-C",
                repo_path,
                "commit",
                "--allow-empty",
                "-m",
                "Initial commit",
            ],
            timeout_seconds=60,
        )
        if not commit.ok:
            raise RuntimeError(commit.stderr.strip() or "failed to create initial commit")

    async def resolve_base_branch(self, repo_path: str, preferred: Optional[str] = None) -> str:
        """
        Return a local branch that exists and can anchor a new worktree.
        Fresh `git init` repos have no commits yet, so `main` is not a valid ref until seeded.
        """
        seen: set[str] = set()
        candidates: List[str] = []
        for value in [preferred, "main", "master"]:
            name = (value or "").strip()
            if name and name not in seen:
                seen.add(name)
                candidates.append(name)

        current = await self._run(["git", "-C", repo_path, "branch", "--show-current"])
        current_name = (current.stdout or "").strip()
        if current_name and current_name not in seen:
            candidates.insert(0, current_name)
            seen.add(current_name)

        for name in candidates:
            if await self._branch_exists(repo_path, name):
                return name

        if not await self._has_commits(repo_path):
            seed_branch = (preferred or "main").strip() or "main"
            await self._create_initial_commit(repo_path, seed_branch)
            if await self._branch_exists(repo_path, seed_branch):
                return seed_branch

        branches = await self._run(
            ["git", "-C", repo_path, "for-each-ref", "--format=%(refname:short)", "refs/heads/"]
        )
        for line in (branches.stdout or "").splitlines():
            name = line.strip()
            if name:
                return name

        raise RuntimeError(
            "repository has no branches to base a worktree on; add at least one commit"
        )

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

    def resolve_run_branch_name(self, run_id: int, prefix: str = "mas/quick-run") -> str:
        return f"{self._slug(prefix)}/{run_id}"

    async def create_continuation_worktree(
        self,
        repo_path: str,
        project_id: int,
        run_id: int,
        source_run_id: int,
        base_branch: str = "main",
        prefix: str = "mas/quick-run",
        worktree_base_path: Optional[str] = None,
    ) -> WorktreePlan:
        """Seed a new run worktree from a prior run's branch or worktree path."""
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            raise RuntimeError(valid.get("error") or "invalid repository")
        canonical_repo_path = str(valid.get("repo_path") or repo_path)

        source_branch = self.resolve_run_branch_name(source_run_id, prefix)
        source_worktree_path = self.resolve_worktree_path(
            repo_path=canonical_repo_path,
            project_id=project_id,
            run_id=source_run_id,
            worktree_base_path=worktree_base_path,
        )

        source_ref: Optional[str] = None
        if await self._branch_exists(canonical_repo_path, source_branch):
            source_ref = source_branch
        elif Path(source_worktree_path).exists():
            if await self._worktree_has_changes(source_worktree_path):
                await self.commit_changes(
                    worktree_path=source_worktree_path,
                    message=f"MAS continuation snapshot from run {source_run_id}",
                )
            source_ref = source_worktree_path
        else:
            return await self.create_worktree(
                repo_path=canonical_repo_path,
                project_id=project_id,
                run_id=run_id,
                base_branch=base_branch,
                prefix=prefix,
                worktree_base_path=worktree_base_path,
            )

        branch_name = self.resolve_run_branch_name(run_id, prefix)
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

        branch_exists = await self._branch_exists(canonical_repo_path, branch_name)
        if branch_exists:
            command = [
                "git",
                "-C",
                canonical_repo_path,
                "worktree",
                "add",
                worktree_path,
                branch_name,
            ]
        else:
            command = [
                "git",
                "-C",
                canonical_repo_path,
                "worktree",
                "add",
                "-b",
                branch_name,
                worktree_path,
                source_ref,
            ]

        result = await self._run(command, timeout_seconds=60)
        if not result.ok:
            raise RuntimeError(
                f"failed to create continuation worktree: {' '.join(command)} :: {result.stderr.strip()}"
            )

        return WorktreePlan(
            branch_name=branch_name,
            worktree_path=worktree_path,
            create_commands=[command],
            reuse_existing_branch=branch_exists,
        )

    async def _worktree_has_changes(self, worktree_path: str) -> bool:
        status = await self._run(["git", "-C", worktree_path, "status", "--porcelain"])
        return bool([line for line in status.stdout.splitlines() if line.strip()])

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
        base_branch = await self.resolve_base_branch(canonical_repo_path, base_branch)

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

    def resolve_persistent_worktree_path(
        self,
        *,
        repo_path: str,
        project_id: int,
        branch_suffix: str,
        worktree_base_path: Optional[str] = None,
    ) -> str:
        repo_root = Path(repo_path).resolve()
        if worktree_base_path:
            base = Path(worktree_base_path).expanduser()
            if not base.is_absolute():
                base = (repo_root / base).resolve()
        else:
            base = repo_root / ".midnight" / "worktrees"
        return str(base / str(project_id) / branch_suffix)

    async def ensure_persistent_worktree(
        self,
        repo_path: str,
        project_id: int,
        branch_name: str,
        base_branch: str = "main",
        worktree_base_path: Optional[str] = None,
    ) -> WorktreePlan:
        """Create (or reuse) a persistent worktree on a fixed branch, e.g. mas/working or mas/preview.

        Unlike create_worktree (per-run mas/quick-run/{run_id} branches), this returns the
        same worktree path/branch across calls so milestone progress persists between runs.
        """
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            raise RuntimeError(valid.get("error") or "invalid repository")
        canonical_repo_path = str(valid.get("repo_path") or repo_path)
        base_branch = await self.resolve_base_branch(canonical_repo_path, base_branch)

        branch_suffix = self._slug(branch_name.split("/")[-1]) or "working"
        worktree_path = self.resolve_persistent_worktree_path(
            repo_path=canonical_repo_path,
            project_id=project_id,
            branch_suffix=branch_suffix,
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

        branch_exists = await self._branch_exists(canonical_repo_path, branch_name)
        if branch_exists:
            command = ["git", "-C", canonical_repo_path, "worktree", "add", worktree_path, branch_name]
        else:
            command = [
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

        result = await self._run(command, timeout_seconds=60)
        if not result.ok:
            raise RuntimeError(
                f"failed to create persistent worktree: {' '.join(command)} :: {result.stderr.strip()}"
            )

        return WorktreePlan(
            branch_name=branch_name,
            worktree_path=worktree_path,
            create_commands=[command],
            reuse_existing_branch=branch_exists,
        )

    async def tag_milestone(
        self,
        repo_path: str,
        *,
        project_id: int,
        run_id: int,
        milestone_index: int,
        milestone_name: str,
        branch: str = "mas/working",
    ) -> Dict[str, Any]:
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return {"ok": False, "error": valid.get("error") or "invalid repository"}
        canonical_repo_path = str(valid.get("repo_path") or repo_path)

        rev = await self._run(["git", "-C", canonical_repo_path, "rev-parse", branch])
        if not rev.ok or not rev.stdout.strip():
            return {"ok": False, "error": f"branch '{branch}' has no commits to tag"}
        commit_hash = rev.stdout.strip()

        tag_name = f"mas/{project_id}/run-{run_id}/m{milestone_index}-{self._slug(milestone_name)}"
        tag_result = await self._run(
            [
                "git",
                "-C",
                canonical_repo_path,
                "tag",
                "-a",
                tag_name,
                commit_hash,
                "-m",
                f"Milestone {milestone_index}: {milestone_name}",
            ],
            timeout_seconds=30,
        )
        return {
            "ok": tag_result.ok,
            "tag": tag_name,
            "commit_hash": commit_hash,
            "stderr": tag_result.stderr.strip(),
        }

    async def promote_branch(
        self,
        repo_path: str,
        *,
        from_branch: str,
        to_branch: str,
        worktree_base_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fast-forward to_branch to from_branch's commit and sync any worktree checked out on it.

        Used to mirror mas/working -> mas/preview at milestone boundaries (no merges/conflicts:
        preview is always a hard mirror of working at the moment of promotion).
        """
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return {"ok": False, "error": valid.get("error") or "invalid repository"}
        canonical_repo_path = str(valid.get("repo_path") or repo_path)

        from_rev = await self._run(["git", "-C", canonical_repo_path, "rev-parse", from_branch])
        if not from_rev.ok or not from_rev.stdout.strip():
            return {"ok": False, "error": f"branch '{from_branch}' has no commits"}
        commit_hash = from_rev.stdout.strip()

        to_exists = await self._branch_exists(canonical_repo_path, to_branch)
        if to_exists:
            update = await self._run(
                ["git", "-C", canonical_repo_path, "update-ref", f"refs/heads/{to_branch}", commit_hash]
            )
        else:
            update = await self._run(["git", "-C", canonical_repo_path, "branch", to_branch, commit_hash])
        if not update.ok:
            return {"ok": False, "error": update.stderr.strip() or f"failed to update {to_branch}"}

        synced_worktree: Optional[str] = None
        for row in await self.list_worktrees(canonical_repo_path):
            if row.get("branch") == to_branch:
                worktree_path = str(row.get("worktree_path") or "")
                if worktree_path and Path(worktree_path).exists():
                    reset = await self._run(
                        ["git", "-C", worktree_path, "reset", "--hard", commit_hash],
                        timeout_seconds=60,
                    )
                    if reset.ok:
                        synced_worktree = worktree_path
                break

        return {
            "ok": True,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "commit_hash": commit_hash,
            "synced_worktree": synced_worktree,
        }

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

    async def cleanup_run_workspace(
        self,
        *,
        repo_path: str,
        project_id: int,
        run_id: int,
        branch_name: Optional[str] = None,
        worktree_base_path: Optional[str] = None,
        run_artifact_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove run worktree/branch and local run artifacts using git/filesystem only (no agent).
        """
        import shutil

        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return {"ok": False, "error": valid.get("error") or "invalid repository"}

        canonical_repo_path = str(valid.get("repo_path") or repo_path)
        worktree_path = self.resolve_worktree_path(
            repo_path=canonical_repo_path,
            project_id=project_id,
            run_id=run_id,
            worktree_base_path=worktree_base_path,
        )
        branch = (branch_name or "").strip() or f"{self._slug('mas/quick-run')}/{run_id}"
        actions: List[Dict[str, Any]] = []

        listed = await self.list_worktrees(canonical_repo_path)
        known_paths = {str(row.get("worktree_path") or "") for row in listed}
        if worktree_path in known_paths:
            remove = await self._run(
                ["git", "-C", canonical_repo_path, "worktree", "remove", "--force", worktree_path],
                timeout_seconds=60,
            )
            actions.append(
                {
                    "action": "worktree_remove",
                    "ok": remove.ok,
                    "stderr": remove.stderr.strip(),
                }
            )
        elif Path(worktree_path).exists():
            prune = await self._run(
                ["git", "-C", canonical_repo_path, "worktree", "prune"],
                timeout_seconds=30,
            )
            actions.append({"action": "worktree_prune", "ok": prune.ok, "stderr": prune.stderr.strip()})
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
                actions.append({"action": "rmtree_worktree_path", "ok": True})
            except OSError as exc:
                actions.append({"action": "rmtree_worktree_path", "ok": False, "error": str(exc)})

        if await self._branch_exists(canonical_repo_path, branch):
            delete_branch = await self._run(
                ["git", "-C", canonical_repo_path, "branch", "-D", branch],
                timeout_seconds=30,
            )
            actions.append(
                {
                    "action": "branch_delete",
                    "branch": branch,
                    "ok": delete_branch.ok,
                    "stderr": delete_branch.stderr.strip(),
                }
            )

        if run_artifact_dir:
            artifact_path = Path(run_artifact_dir)
            if artifact_path.exists():
                try:
                    shutil.rmtree(artifact_path, ignore_errors=True)
                    actions.append({"action": "rmtree_run_artifacts", "ok": True, "path": str(artifact_path)})
                except OSError as exc:
                    actions.append(
                        {
                            "action": "rmtree_run_artifacts",
                            "ok": False,
                            "path": str(artifact_path),
                            "error": str(exc),
                        }
                    )

        ok = all(item.get("ok", True) for item in actions if "ok" in item)
        return {
            "ok": ok,
            "repo_path": canonical_repo_path,
            "worktree_path": worktree_path,
            "branch_name": branch,
            "actions": actions,
        }

    def project_worktree_root(
        self,
        *,
        repo_path: str,
        project_id: int,
        worktree_base_path: Optional[str] = None,
    ) -> Path:
        repo_root = Path(repo_path).resolve()
        if worktree_base_path:
            base = Path(worktree_base_path).expanduser()
            if not base.is_absolute():
                base = (repo_root / base).resolve()
        else:
            base = repo_root / ".midnight" / "worktrees"
        return base / str(project_id)

    async def discover_project_worktree_paths(
        self,
        *,
        repo_path: str,
        project_id: int,
        worktree_base_path: Optional[str] = None,
    ) -> List[str]:
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return []
        canonical_repo_path = str(valid.get("repo_path") or repo_path)
        paths: set[str] = set()
        project_root = self.project_worktree_root(
            repo_path=canonical_repo_path,
            project_id=project_id,
            worktree_base_path=worktree_base_path,
        )
        if project_root.is_dir():
            for child in project_root.iterdir():
                if child.is_dir():
                    paths.add(str(child.resolve()))
        needle = f"{project_id}{'/' if '/' in canonical_repo_path else chr(92)}"
        for row in await self.list_worktrees(canonical_repo_path):
            worktree_path = str(row.get("worktree_path") or "")
            normalized = worktree_path.replace("\\", "/")
            if f"/{project_id}/" in normalized or normalized.endswith(f"/{project_id}"):
                paths.add(worktree_path)
        return sorted(paths)

    async def create_project_snapshot_tag(
        self,
        *,
        repo_path: str,
        project_id: int,
        version: int,
        reason: str,
        worktree_base_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return {"ok": False, "error": valid.get("error") or "invalid repository"}

        canonical_repo_path = str(valid.get("repo_path") or repo_path)
        worktrees = await self.discover_project_worktree_paths(
            repo_path=canonical_repo_path,
            project_id=project_id,
            worktree_base_path=worktree_base_path,
        )
        snapshot_commit: Optional[str] = None
        snapshot_worktree: Optional[str] = None
        ordered = sorted(
            worktrees,
            key=lambda path: Path(path).stat().st_mtime if Path(path).exists() else 0,
            reverse=True,
        )
        for worktree_path in ordered:
            if not Path(worktree_path).exists():
                continue
            commit = await self.commit_changes(
                worktree_path=worktree_path,
                message=f"MAS project {project_id} snapshot v{version} before refresh: {reason}",
            )
            if commit.get("commit_hash"):
                snapshot_commit = str(commit["commit_hash"])
                snapshot_worktree = worktree_path
                break
            rev = await self._run(["git", "-C", worktree_path, "rev-parse", "HEAD"])
            if rev.ok and rev.stdout.strip():
                snapshot_commit = rev.stdout.strip()
                snapshot_worktree = worktree_path
                break

        if not snapshot_commit:
            rev = await self._run(["git", "-C", canonical_repo_path, "rev-parse", "HEAD"])
            if rev.ok:
                snapshot_commit = rev.stdout.strip()

        tag_name = f"mas/project-{project_id}/v{version}"
        if not snapshot_commit:
            return {
                "ok": False,
                "error": "no commit available for snapshot tag",
                "tag": tag_name,
                "worktree_path": snapshot_worktree,
            }

        tag_result = await self._run(
            [
                "git",
                "-C",
                canonical_repo_path,
                "tag",
                "-a",
                tag_name,
                snapshot_commit,
                "-m",
                reason[:500] or f"Project {project_id} snapshot v{version}",
            ],
            timeout_seconds=30,
        )
        return {
            "ok": tag_result.ok,
            "tag": tag_name,
            "commit_hash": snapshot_commit,
            "worktree_path": snapshot_worktree,
            "stderr": tag_result.stderr.strip(),
        }

    async def cleanup_project_worktrees(
        self,
        *,
        repo_path: str,
        project_id: int,
        worktree_base_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        import shutil

        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return {"ok": False, "error": valid.get("error") or "invalid repository"}

        canonical_repo_path = str(valid.get("repo_path") or repo_path)
        actions: List[Dict[str, Any]] = []
        worktree_paths = await self.discover_project_worktree_paths(
            repo_path=canonical_repo_path,
            project_id=project_id,
            worktree_base_path=worktree_base_path,
        )
        known = {str(row.get("worktree_path") or "") for row in await self.list_worktrees(canonical_repo_path)}

        for worktree_path in worktree_paths:
            if worktree_path in known:
                remove = await self._run(
                    ["git", "-C", canonical_repo_path, "worktree", "remove", "--force", worktree_path],
                    timeout_seconds=60,
                )
                actions.append(
                    {
                        "action": "worktree_remove",
                        "path": worktree_path,
                        "ok": remove.ok,
                        "stderr": remove.stderr.strip(),
                    }
                )
            elif Path(worktree_path).exists():
                try:
                    shutil.rmtree(worktree_path, ignore_errors=True)
                    actions.append({"action": "rmtree_worktree_path", "path": worktree_path, "ok": True})
                except OSError as exc:
                    actions.append(
                        {
                            "action": "rmtree_worktree_path",
                            "path": worktree_path,
                            "ok": False,
                            "error": str(exc),
                        }
                    )

        await self._run(["git", "-C", canonical_repo_path, "worktree", "prune"], timeout_seconds=30)
        project_root = self.project_worktree_root(
            repo_path=canonical_repo_path,
            project_id=project_id,
            worktree_base_path=worktree_base_path,
        )
        if project_root.exists():
            try:
                shutil.rmtree(project_root, ignore_errors=True)
                actions.append({"action": "rmtree_project_worktree_root", "path": str(project_root), "ok": True})
            except OSError as exc:
                actions.append(
                    {
                        "action": "rmtree_project_worktree_root",
                        "path": str(project_root),
                        "ok": False,
                        "error": str(exc),
                    }
                )

        ok = all(item.get("ok", True) for item in actions if "ok" in item)
        return {"ok": ok, "actions": actions, "repo_path": canonical_repo_path}

    async def delete_run_branches(
        self,
        repo_path: str,
        run_ids: List[int],
        *,
        prefix: str = "mas/quick-run",
    ) -> Dict[str, Any]:
        valid = await self.validate_repository(repo_path)
        if not valid.get("ok"):
            return {"ok": False, "error": valid.get("error") or "invalid repository"}
        canonical_repo_path = str(valid.get("repo_path") or repo_path)
        branch_prefix = self._slug(prefix)
        actions: List[Dict[str, Any]] = []
        for run_id in run_ids:
            branch = f"{branch_prefix}/{run_id}"
            if await self._branch_exists(canonical_repo_path, branch):
                delete_branch = await self._run(
                    ["git", "-C", canonical_repo_path, "branch", "-D", branch],
                    timeout_seconds=30,
                )
                actions.append(
                    {
                        "action": "branch_delete",
                        "branch": branch,
                        "ok": delete_branch.ok,
                        "stderr": delete_branch.stderr.strip(),
                    }
                )
        ok = all(item.get("ok", True) for item in actions if "ok" in item)
        return {"ok": ok, "actions": actions}

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
