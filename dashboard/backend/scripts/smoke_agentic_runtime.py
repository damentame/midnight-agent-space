"""
Lightweight smoke checks for quick-run runtime safety defaults.

Run:
    python -m dashboard.backend.scripts.smoke_agentic_runtime
"""

from dashboard.backend.services.codex_cli_runner import (
    CodexCliCapabilities,
    CodexCliRunPlan,
    codex_cli_runner,
)
from dashboard.backend.services.git_worktree_service import git_worktree_service


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    capabilities = CodexCliCapabilities(
        supports_exec=True,
        supports_json=True,
        supports_ask_for_approval=True,
        supports_sandbox=True,
        supports_cd=True,
    )

    dangerous_plan = CodexCliRunPlan(
        prompt="smoke",
        model="gpt-4.1-mini",
        worktree_path="C:/tmp/worktree",
        approval_mode="never",
        sandbox_mode="danger-full-access",
    )
    dangerous_cmd = codex_cli_runner.build_command("codex", dangerous_plan, capabilities)
    approval_idx = dangerous_cmd.index("--ask-for-approval")
    sandbox_idx = dangerous_cmd.index("--sandbox")
    _assert(dangerous_cmd[approval_idx + 1] == "never", "approval mode 'never' should remain unchanged")
    _assert(dangerous_cmd[sandbox_idx + 1] == "workspace-write", "dangerous sandbox mode was not sanitized")

    safe_plan = CodexCliRunPlan(
        prompt="smoke",
        model="gpt-4.1-mini",
        worktree_path="C:/tmp/worktree",
        approval_mode="on-request",
        sandbox_mode="workspace-write",
    )
    safe_cmd = codex_cli_runner.build_command("codex", safe_plan, capabilities)
    safe_approval_idx = safe_cmd.index("--ask-for-approval")
    safe_sandbox_idx = safe_cmd.index("--sandbox")
    _assert(safe_cmd[safe_approval_idx + 1] == "on-request", "safe approval mode was unexpectedly changed")
    _assert(safe_cmd[safe_sandbox_idx + 1] == "workspace-write", "safe sandbox mode was unexpectedly changed")

    dangerous_approval_plan = CodexCliRunPlan(
        prompt="smoke",
        model="gpt-4.1-mini",
        worktree_path="C:/tmp/worktree",
        approval_mode="dangerously-disabled",
        sandbox_mode="workspace-write",
    )
    dangerous_approval_cmd = codex_cli_runner.build_command("codex", dangerous_approval_plan, capabilities)
    dangerous_approval_idx = dangerous_approval_cmd.index("--ask-for-approval")
    _assert(
        dangerous_approval_cmd[dangerous_approval_idx + 1] == "never",
        "dangerous approval mode was not sanitized to 'never'",
    )

    default_worktree = git_worktree_service.resolve_worktree_path(
        repo_path="C:/tmp/repo",
        project_id=5,
        run_id=9,
    ).replace("\\", "/")
    _assert(
        default_worktree.endswith("/.midnight/worktrees/5/9"),
        "default worktree path does not match .midnight/worktrees/{project_id}/{run_id}",
    )

    custom_worktree = git_worktree_service.resolve_worktree_path(
        repo_path="C:/tmp/repo",
        project_id=5,
        run_id=9,
        worktree_base_path="alt-worktrees",
    ).replace("\\", "/")
    _assert(
        custom_worktree.endswith("/alt-worktrees/5/9"),
        "custom worktree base path was not applied",
    )

    print("smoke_agentic_runtime: OK")


if __name__ == "__main__":
    main()
