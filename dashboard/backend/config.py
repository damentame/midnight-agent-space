"""
Configuration: reads DB + Temporal from temporal/.env at repo root.
"""
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv


def _load_dotenv_files() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    for p in (root / "temporal" / ".env", root / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


_load_dotenv_files()


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def _env_int(*names: str, default: int) -> int:
    raw = _env(*names, default=str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _normalize_db_host(host: str) -> str:
    """Windows often resolves localhost to ::1 while Postgres listens on IPv4 only."""
    value = (host or "").strip() or "127.0.0.1"
    if value.lower() in {"localhost", "::1"}:
        return "127.0.0.1"
    return value


class DatabaseConfig:
    host: str = _normalize_db_host(os.getenv("DB_HOST", "127.0.0.1"))
    port: int = int(os.getenv("DB_PORT", "5434"))
    name: str = os.getenv("DB_NAME", "midnight_agent_space_dev")
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "7714")
    min_connections: int = int(os.getenv("DB_POOL_MIN", "1"))
    max_connections: int = int(os.getenv("DB_POOL_MAX", "10"))


class TemporalConfig:
    host: str = os.getenv("TEMPORAL_HOST", "localhost")
    port: int = int(os.getenv("TEMPORAL_PORT", "7233"))
    namespace: str = os.getenv("TEMPORAL_NAMESPACE", "default")


class AppConfig:
    api_host: str = os.getenv("DASHBOARD_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("DASHBOARD_API_PORT", "8001"))
    debug: bool = os.getenv("DASHBOARD_DEBUG", "true").lower() in ("1", "true", "yes")
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    upload_max_size: int = _env_int(
        "UPLOAD_MAX_SIZE",
        "MIDNIGHT_UPLOAD_MAX_SIZE",
        default=50 * 1024 * 1024,
    )
    allowed_extensions: frozenset = frozenset(
        {
            ".txt",
            ".md",
            ".json",
            ".csv",
            ".xml",
            ".pdf",
            ".docx",
            ".fig",
            ".figma",
            ".gif",
            ".jpeg",
            ".jpg",
            ".py",
            ".png",
            ".sketch",
            ".js",
            ".svg",
            ".ts",
            ".tsx",
            ".webp",
        }
    )
    workspace_root: str = os.getenv("WORKSPACE_ROOT", "")
    codex_cli_bin: str = _env("CODEX_COMMAND", "CODEX_CLI_BIN", default="codex")
    codex_cli_model: str = _env("CODEX_CLI_MODEL", default="")
    codex_cli_model_fast: str = _env("CODEX_CLI_MODEL_FAST", default="gpt-4.1-mini")
    codex_cli_model_complex: str = _env("CODEX_CLI_MODEL_COMPLEX", default="gpt-4.1")
    codex_cli_timeout_seconds: int = _env_int(
        "CODEX_DEFAULT_TIMEOUT_SECONDS",
        "CODEX_CLI_TIMEOUT_SECONDS",
        default=900,
    )
    codex_sandbox_mode: str = _env(
        "CODEX_SANDBOX_MODE",
        "CODEX_CLI_SANDBOX_MODE",
        default="workspace-write",
    )
    codex_approval_mode: str = _env(
        "CODEX_APPROVAL_MODE",
        "CODEX_CLI_APPROVAL_MODE",
        default="never",
    )
    midnight_worktree_base_path: str = _env(
        "MIDNIGHT_WORKTREE_BASE_PATH",
        "CODEX_CLI_WORKTREE_BASE_PATH",
        default="",
    )
    midnight_run_artifact_path: str = _env(
        "MIDNIGHT_RUN_ARTIFACT_PATH",
        "CODEX_CLI_RUN_ARTIFACT_PATH",
        default="",
    )
    midnight_max_concurrency: int = max(
        1,
        _env_int("MIDNIGHT_MAX_CONCURRENCY", "CODEX_CLI_MAX_CONCURRENCY", default=4),
    )
    section_task_max_parallel: int = max(
        1,
        _env_int("SECTION_TASK_MAX_PARALLEL", default=4),
    )
    parallel_cli_stagger_seconds: float = max(
        0.0,
        float(_env("PARALLEL_CLI_STAGGER_SECONDS", default="2.0") or 2.0),
    )
    midnight_default_runtime: str = _env(
        "MIDNIGHT_DEFAULT_RUNTIME",
        "CODEX_CLI_DEFAULT_RUNTIME",
        default="codex-cli",
    )
    claude_cli_bin: str = _env("CLAUDE_COMMAND", "CLAUDE_CLI_BIN", default="claude")
    claude_cli_model: str = _env("CLAUDE_CLI_MODEL", default="sonnet")
    claude_cli_model_fast: str = _env("CLAUDE_CLI_MODEL_FAST", default="haiku")
    claude_cli_model_complex: str = _env("CLAUDE_CLI_MODEL_COMPLEX", default="sonnet")
    claude_cli_timeout_seconds: int = _env_int(
        "CLAUDE_CLI_TIMEOUT_SECONDS",
        default=900,
    )
    claude_permission_mode: str = _env(
        "CLAUDE_PERMISSION_MODE",
        "CLAUDE_CLI_PERMISSION_MODE",
        default="acceptEdits",
    )
    claude_allowed_tools: str = _env(
        "CLAUDE_ALLOWED_TOOLS",
        "CLAUDE_CLI_ALLOWED_TOOLS",
        default="Read,Edit,Write,Glob,Grep,Bash",
    )
    cursor_agent_bin: str = _env(
        "CURSOR_AGENT_COMMAND",
        "CURSOR_AGENT_BIN",
        default="cursor-agent",
    )
    cursor_agent_model: str = _env("CURSOR_AGENT_MODEL", default="")
    cursor_agent_model_fast: str = _env("CURSOR_AGENT_MODEL_FAST", default="")
    cursor_agent_model_complex: str = _env("CURSOR_AGENT_MODEL_COMPLEX", default="")
    cursor_agent_timeout_seconds: int = _env_int("CURSOR_AGENT_TIMEOUT_SECONDS", default=900)
    midnight_reviewer_runtime: str = _env(
        "MIDNIGHT_REVIEWER_RUNTIME",
        default="claude-cli",
    )
    hermes_enabled: bool = os.getenv("HERMES_ENABLED", "false").lower() in ("1", "true", "yes")
    hermes_command: str = os.getenv("HERMES_COMMAND", "hermes")
    hermes_api_url: str = os.getenv("HERMES_API_URL", "")
    figma_access_token: str = _env("FIGMA_ACCESS_TOKEN", "FIGMA_API_TOKEN", default="")
    context_pack_max_documents: int = _env_int("CONTEXT_PACK_MAX_DOCUMENTS", default=8)
    context_pack_task_max_documents: int = _env_int("CONTEXT_PACK_TASK_MAX_DOCUMENTS", default=4)
    context_pack_preview_chars: int = _env_int("CONTEXT_PACK_PREVIEW_CHARS", default=480)
    context_pack_figma_preview_chars: int = _env_int("CONTEXT_PACK_FIGMA_PREVIEW_CHARS", default=3000)
    context_pack_max_json_chars: int = _env_int("CONTEXT_PACK_MAX_JSON_CHARS", default=48000)
    context_pack_use_architecture_cache: bool = os.getenv(
        "CONTEXT_PACK_USE_ARCHITECTURE_CACHE", "true"
    ).lower() in ("1", "true", "yes")
    token_budget_warn_on_task: bool = os.getenv("TOKEN_BUDGET_WARN_ON_TASK", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    context_pack_include_change_history: bool = os.getenv(
        "CONTEXT_PACK_INCLUDE_CHANGE_HISTORY", "false"
    ).lower() in ("1", "true", "yes")
    context_pack_figma_section_chars: int = _env_int("CONTEXT_PACK_FIGMA_SECTION_CHARS", default=8000)
    figma_extraction_version: str = _env("FIGMA_EXTRACTION_VERSION", default="v2")
    figma_max_section_nodes: int = _env_int("FIGMA_MAX_SECTION_NODES", default=500)
    figma_max_section_exports: int = _env_int("FIGMA_MAX_SECTION_EXPORTS", default=12)
    figma_max_assets: int = _env_int("FIGMA_MAX_ASSETS", default=50)
    figma_max_text_len: int = _env_int("FIGMA_MAX_TEXT_LEN", default=2000)
    figma_require_node_id: bool = os.getenv("FIGMA_REQUIRE_NODE_ID", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    figma_require_resolved_fonts: bool = os.getenv("FIGMA_REQUIRE_RESOLVED_FONTS", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    figma_section_slice_height: int = _env_int("FIGMA_SECTION_SLICE_HEIGHT", default=900)
    design_fidelity_structural_block: bool = os.getenv(
        "DESIGN_FIDELITY_STRUCTURAL_BLOCK", "true"
    ).lower() in ("1", "true", "yes")
    design_fidelity_visual_advisory: bool = os.getenv(
        "DESIGN_FIDELITY_VISUAL_ADVISORY", "true"
    ).lower() in ("1", "true", "yes")


db_config = DatabaseConfig()
temporal_config = TemporalConfig()
app_config = AppConfig()


def get_database_dsn() -> str:
    c = db_config
    return f"postgresql://{c.user}:{c.password}@{c.host}:{c.port}/{c.name}"


def get_temporal_address() -> str:
    return f"{temporal_config.host}:{temporal_config.port}"
