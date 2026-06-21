from __future__ import annotations

import os
import shutil
from typing import Any, Dict

from ..config import app_config
from .model_routing_service import model_catalog


class RuntimeCheckService:
    def runtime_check(self) -> Dict[str, Any]:
        codex_bin = app_config.codex_cli_bin
        codex_path = shutil.which(codex_bin) if codex_bin else None
        git_path = shutil.which("git")
        hermes_enabled = bool(app_config.hermes_enabled)

        claude_bin = app_config.claude_cli_bin
        claude_path = shutil.which(claude_bin) if claude_bin else None

        cursor_bin = app_config.cursor_agent_bin
        cursor_path = shutil.which(cursor_bin) if cursor_bin else None
        if not cursor_path and cursor_bin != "agent":
            cursor_path = shutil.which("agent")

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
            "claude_cli": {
                "configured_binary": claude_bin,
                "found": bool(claude_path),
                "path": claude_path,
                "default_model": app_config.claude_cli_model,
                "permission_mode": app_config.claude_permission_mode,
                "allowed_tools": app_config.claude_allowed_tools,
                "timeout_seconds": app_config.claude_cli_timeout_seconds,
            },
            "cursor_agent": {
                "configured_binary": cursor_bin,
                "found": bool(cursor_path),
                "path": cursor_path,
                "default_model": app_config.cursor_agent_model or None,
                "timeout_seconds": app_config.cursor_agent_timeout_seconds,
            },
            "cli_runtimes": [
                {
                    "id": "codex-cli",
                    "label": "Codex CLI",
                    "found": bool(codex_path),
                    "configured_binary": codex_bin,
                    "default_model": app_config.codex_cli_model or None,
                },
                {
                    "id": "claude-cli",
                    "label": "Claude CLI",
                    "found": bool(claude_path),
                    "configured_binary": claude_bin,
                    "default_model": app_config.claude_cli_model or None,
                },
                {
                    "id": "cursor-agent",
                    "label": "Cursor Agent",
                    "found": bool(cursor_path),
                    "configured_binary": cursor_bin,
                    "default_model": app_config.cursor_agent_model or None,
                },
            ],
            "reviewer_runtime": {
                "default": app_config.midnight_reviewer_runtime,
                "options": ["claude-cli", "codex-cli"],
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
            "model_catalog": model_catalog(),
        }


runtime_check_service = RuntimeCheckService()
