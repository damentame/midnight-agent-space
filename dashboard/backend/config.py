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


db_config = DatabaseConfig()
temporal_config = TemporalConfig()
app_config = AppConfig()


def get_database_dsn() -> str:
    c = db_config
    return f"postgresql://{c.user}:{c.password}@{c.host}:{c.port}/{c.name}"


def get_temporal_address() -> str:
    return f"{temporal_config.host}:{temporal_config.port}"
