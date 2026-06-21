"""Worktree continuation for re-execute with completed tasks."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dashboard.backend.services.git_worktree_service import GitWorktreeService


@pytest.mark.asyncio
async def test_resolve_run_branch_name() -> None:
    service = GitWorktreeService()
    assert service.resolve_run_branch_name(39) == "mas-quick-run/39"


@pytest.mark.asyncio
async def test_create_continuation_worktree_from_existing_path(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    source_wt = tmp_path / "worktrees" / "5" / "39"
    source_wt.mkdir(parents=True)
    (source_wt / "app.js").write_text("console.log('done')", encoding="utf-8")

    service = GitWorktreeService()
    service.validate_repository = AsyncMock(return_value={"ok": True, "repo_path": str(repo)})
    service._branch_exists = AsyncMock(return_value=False)
    service._worktree_has_changes = AsyncMock(return_value=False)
    service.list_worktrees = AsyncMock(return_value=[])
    service._run = AsyncMock(return_value=MagicMock(ok=True, stderr=""))

    with patch.object(
        service,
        "resolve_worktree_path",
        side_effect=lambda **kwargs: str(
            tmp_path / "worktrees" / str(kwargs["project_id"]) / str(kwargs["run_id"])
        ),
    ):
        plan = await service.create_continuation_worktree(
            repo_path=str(repo),
            project_id=5,
            run_id=40,
            source_run_id=39,
        )

    assert plan.worktree_path.endswith("40")
    command = service._run.await_args_list[0][0][0]
    assert "worktree" in command
    assert "add" in command
    assert str(source_wt) in command or any(str(source_wt) == arg for arg in command)


@pytest.mark.asyncio
async def test_resolve_continuation_source_run_id_prefers_existing_worktree() -> None:
    from dashboard.backend.services.run_service import RunService

    service = RunService()
    db = MagicMock()
    service.list_runs = AsyncMock(
        return_value=[
            {"agent_run_id": 40, "result_payload": {}},
            {"agent_run_id": 39, "result_payload": {}},
        ]
    )

    with patch("dashboard.backend.services.run_service.Path") as path_cls:
        path_cls.return_value.exists.return_value = True
        with patch(
            "dashboard.backend.services.run_service.git_worktree_service.resolve_worktree_path",
            return_value="/wt/5/39",
        ):
            result = await service._resolve_continuation_source_run_id(
                db, project_id=5, repo_path="/repo", explicit=None
            )
    assert result == 40
