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


class DatabaseConfig:
    host: str = os.getenv("DB_HOST", "localhost")
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
    upload_max_size: int = 50 * 1024 * 1024
    allowed_extensions: frozenset = frozenset(
        {
            ".txt",
            ".md",
            ".json",
            ".csv",
            ".xml",
            ".pdf",
            ".docx",
            ".py",
            ".js",
            ".ts",
            ".tsx",
        }
    )
    workspace_root: str = os.getenv("WORKSPACE_ROOT", "")
    codex_cli_bin: str = _env("CODEX_COMMAND", "CODEX_CLI_BIN", default="codex")
    codex_cli_model: str = _env("CODEX_CLI_MODEL", default="gpt-4.1-mini")
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
        _env_int("MIDNIGHT_MAX_CONCURRENCY", "CODEX_CLI_MAX_CONCURRENCY", default=1),
    )
    midnight_default_runtime: str = _env(
        "MIDNIGHT_DEFAULT_RUNTIME",
        "CODEX_CLI_DEFAULT_RUNTIME",
        default="codex-cli",
    )
    hermes_enabled: bool = os.getenv("HERMES_ENABLED", "false").lower() in ("1", "true", "yes")
    hermes_command: str = os.getenv("HERMES_COMMAND", "hermes")
    hermes_api_url: str = os.getenv("HERMES_API_URL", "")


db_config = DatabaseConfig()
temporal_config = TemporalConfig()
app_config = AppConfig()


def get_database_dsn() -> str:
    c = db_config
    return f"postgresql://{c.user}:{c.password}@{c.host}:{c.port}/{c.name}"


def get_temporal_address() -> str:
    return f"{temporal_config.host}:{temporal_config.port}"
