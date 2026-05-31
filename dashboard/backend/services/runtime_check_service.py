from __future__ import annotations

import os
import shutil
from typing import Any, Dict

from ..config import app_config


class RuntimeCheckService:
    def runtime_check(self) -> Dict[str, Any]:
        codex_bin = app_config.codex_cli_bin
        codex_path = shutil.which(codex_bin) if codex_bin else None
        git_path = shutil.which("git")
        hermes_enabled = bool(app_config.hermes_enabled)

        return {
            "codex_cli": {
                "configured_binary": codex_bin,
                "found": bool(codex_path),
                "path": codex_path,
                "default_model": app_config.codex_cli_model,
                "approval_mode": app_config.codex_approval_mode,
                "sandbox_mode": app_config.codex_sandbox_mode,
                "timeout_seconds": app_config.codex_cli_timeout_seconds,
            },
            "git": {
                "found": bool(git_path),
                "path": git_path,
            },
            "workspace_root": app_config.workspace_root,
            "midnight": {
                "default_runtime": app_config.midnight_default_runtime,
                "max_concurrency": app_config.midnight_max_concurrency,
                "worktree_base_path": app_config.midnight_worktree_base_path or None,
                "run_artifact_path": app_config.midnight_run_artifact_path or None,
            },
            "hermes": {
                "enabled": hermes_enabled,
                "status": "disabled" if not hermes_enabled else "enabled",
                "api_url": app_config.hermes_api_url if hermes_enabled else None,
            },
            "environment": {
                "agent_provider_default": os.getenv("AGENT_PROVIDER_DEFAULT", "cursor"),
            },
        }


runtime_check_service = RuntimeCheckService()
