"""Configuration management for Temporal workflows."""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

# Lazy load .env file to avoid file system operations in workflow sandbox
# This will be loaded when config is first accessed, not at import time
_env_loaded = False

def _load_env_if_needed():
    """Load .env file only when needed (not in workflow sandbox)."""
    global _env_loaded
    if _env_loaded:
        return
    
    # #region agent log
    try:
        with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
            import json
            f.write(json.dumps({"runId":"init","hypothesisId":"G","location":"config.py:17","message":"_load_env_if_needed called","data":{},"timestamp":__import__('time').time()*1000})+'\n')
    except: pass
    # #endregion
    
    # Try to load .env file if we're not in a workflow sandbox
    # Activities and workers can safely load .env files
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        
        # Try to find .env file in temporal directory first, then parent
        # __file__ is config.py, so parent is temporal directory
        env_path = Path(__file__).parent / ".env"
        if not env_path.exists():
            # Try parent directory (project root)
            env_path = Path(__file__).parent.parent / ".env"
        if not env_path.exists():
            # Try alternative name
            env_path = Path(__file__).parent.parent / ".env.temporal"
        
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
        else:
            # Fallback: try to load from current directory or parent
            # This will look for .env in current working directory
            load_dotenv(override=True)
    except Exception as e:
        # If we can't load .env (e.g., in workflow sandbox), that's okay
        # Environment variables should already be set by the worker
        # Log the error for debugging (but don't fail in workflow sandbox)
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Could not load .env file (this is expected in workflow sandbox): {e}")
        # Try to load from environment variables that might already be set
        import os
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning("OPENAI_API_KEY not found in environment after .env load attempt")
        pass
    
    _env_loaded = True


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""
    host: str = Field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = Field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    name: str = Field(default_factory=lambda: os.getenv("DB_NAME", "midnight_agent_space_dev"))
    user: str = Field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    password: str = Field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    
    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class OpenAIConfig(BaseSettings):
    """OpenAI API configuration."""
    api_key: str = Field(default="", env="OPENAI_API_KEY")
    embedding_model: str = Field(default="text-embedding-3-small", env="OPENAI_EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1536, env="OPENAI_EMBEDDING_DIMENSIONS")


class CursorAPIConfig(BaseSettings):
    """Cursor API configuration."""
    api_key: Optional[str] = Field(default=None, env="CURSOR_API_KEY")
    api_url: str = Field(default="https://api.cursor.com/v0", env="CURSOR_API_URL")
    model: str = Field(default="gpt-4o", env="CURSOR_API_MODEL")  # Legacy; not sent as Cloud Agents prompt.model (see model_fast/model_complex).
    # Cursor Cloud Agents: IDs from GET /v0/models. If unset, prompt.model is omitted (account default).
    model_fast: str = Field(default="", env="CURSOR_MODEL_FAST")
    model_complex: str = Field(default="", env="CURSOR_MODEL_COMPLEX")
    # Optional GitHub repository URL which Cursor agents and git/GitHub activities should target,
    # e.g. "https://github.com/your-org/your-repo".
    repository_url: Optional[str] = Field(default=None, env="CURSOR_REPOSITORY")
    # Default base branch to use when creating workflow-specific develop branches.
    default_branch: str = Field(default="main", env="CURSOR_DEFAULT_BRANCH")


class CodexAPIConfig(BaseSettings):
    """
    Codex/OpenAI-based agent provider configuration.

    This reuses the standard OPENAI_API_KEY by default so that agent execution
    can share credentials with embedding and other OpenAI usage, while allowing
    a separate base URL and model to be configured when needed.
    """
    api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    api_url: str = Field(default="https://api.openai.com/v1", env="CODEX_API_URL")
    model: str = Field(default="gpt-4.1-mini", env="CODEX_MODEL")
    # When set, used for execute_mode fast/complex; empty means fall back to `model` (CODEX_MODEL).
    model_fast: str = Field(default="", env="CODEX_MODEL_FAST")
    model_complex: str = Field(default="", env="CODEX_MODEL_COMPLEX")


class ClaudeCodeConfig(BaseSettings):
    """
    Claude Code agent provider configuration.

    Uses the claude-agent-sdk Python package which communicates with a locally
    installed Claude Code CLI.  For headless / programmatic use the
    ANTHROPIC_API_KEY environment variable is required.
    """
    api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-sonnet-4-20250514", env="CLAUDE_CODE_MODEL")
    model_fast: str = Field(default="", env="CLAUDE_CODE_MODEL_FAST")
    model_complex: str = Field(default="", env="CLAUDE_CODE_MODEL_COMPLEX")
    max_turns: int = Field(default=200, env="CLAUDE_CODE_MAX_TURNS")
    permission_mode: str = Field(default="bypassPermissions", env="CLAUDE_CODE_PERMISSION_MODE")
    max_concurrent_sessions: int = Field(default=4, env="CLAUDE_CODE_MAX_CONCURRENT")


class AgentRuntimeConfig(BaseSettings):
    """
    Global agent runtime configuration.

    Controls which agent provider should be used by default when a workflow
    input does not explicitly specify one.
    """
    # Supported providers: "cursor", "codex", "claude-code"
    default_provider: str = Field(default="cursor", env="AGENT_PROVIDER_DEFAULT")


class TemporalConfig(BaseSettings):
    """Temporal server configuration."""
    host: str = Field(default="localhost", env="TEMPORAL_HOST")
    port: int = Field(default=7233, env="TEMPORAL_PORT")
    namespace: str = Field(default="default", env="TEMPORAL_NAMESPACE")
    # Root path for task executor (codebase to build and index for RAG). Set via WORKSPACE_ROOT.
    workspace_root: str = Field(default="", env="WORKSPACE_ROOT")
    
    @property
    def address(self) -> str:
        """Get Temporal server address."""
        return f"{self.host}:{self.port}"


class ChunkingConfig(BaseSettings):
    """Document chunking configuration."""
    chunk_size: int = Field(default=1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, env="CHUNK_OVERLAP")
    chunk_separators: list[str] = Field(
        default=["\n\n", "\n", ". ", " ", ""],
        env="CHUNK_SEPARATORS"
    )


class EmbeddingConfig(BaseSettings):
    """Embedding generation configuration."""
    provider: str = Field(default="openai", env="EMBEDDING_PROVIDER")  # openai, sentence_transformers, ollama, huggingface
    batch_size: int = Field(default=100, env="EMBEDDING_BATCH_SIZE")
    max_retries: int = Field(default=3, env="EMBEDDING_MAX_RETRIES")
    retry_delay: float = Field(default=1.0, env="EMBEDDING_RETRY_DELAY")
    # Sentence Transformers config
    sentence_transformers_model: str = Field(default="all-MiniLM-L6-v2", env="SENTENCE_TRANSFORMERS_MODEL")
    # Ollama config (for embeddings)
    ollama_embedding_model: str = Field(default="nomic-embed-text", env="OLLAMA_EMBEDDING_MODEL")
    ollama_url: str = Field(default="http://localhost:11434", env="OLLAMA_URL")
    # Hugging Face config
    huggingface_api_key: Optional[str] = Field(default=None, env="HUGGINGFACE_API_KEY")
    huggingface_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", env="HUGGINGFACE_MODEL")


class LocalLLMConfig(BaseSettings):
    """Local LLM configuration for document serialization."""
    enabled: bool = Field(default=False, env="LOCAL_LLM_ENABLED")
    url: str = Field(default="http://localhost:11434", env="LOCAL_LLM_URL")
    model: str = Field(default="llama2", env="LOCAL_LLM_MODEL")


class Config(BaseSettings):
    """Main configuration class."""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    cursor_api: CursorAPIConfig = Field(default_factory=CursorAPIConfig)
    codex_api: CodexAPIConfig = Field(default_factory=CodexAPIConfig)
    claude_code: ClaudeCodeConfig = Field(default_factory=ClaudeCodeConfig)
    agent_runtime: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    local_llm: LocalLLMConfig = Field(default_factory=LocalLLMConfig)
    
    class Settings:
        # Don't use env_file here to avoid file system access at import time
        # Environment variables are loaded via _load_env_if_needed() or directly from os.getenv
        extra = "ignore"  # Ignore extra environment variables
        # Disable automatic .env file loading to prevent file system operations
        env_file = None


# Global configuration instance - lazy load .env when first accessed
# In workflow sandbox, skip .env loading and use environment variables directly
_config_instance = None

def _get_config_instance():
    """Get or create config instance, safely handling workflow sandbox."""
    global _config_instance
    if _config_instance is None:
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"init","hypothesisId":"F","location":"config.py:119","message":"_get_config_instance called","data":{},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        # Try to load .env (will fail silently in workflow sandbox)
        # Workers and activities will successfully load .env
        _load_env_if_needed()
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                import os
                f.write(json.dumps({"runId":"init","hypothesisId":"F","location":"config.py:125","message":"After _load_env_if_needed","data":{"OPENAI_API_KEY_set": "OPENAI_API_KEY" in os.environ},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
        _config_instance = Config()
        # Verify API key was loaded - if env var exists but config doesn't have it, set it manually
        import os
        env_key = os.getenv("OPENAI_API_KEY", "")
        if env_key and not _config_instance.openai.api_key:
            # Force set the API key if it exists in environment but wasn't loaded into config
            _config_instance.openai.api_key = env_key
        
        # Verify Cursor API key was loaded - if env var exists but config doesn't have it, set it manually
        cursor_env_key = os.getenv("CURSOR_API_KEY", "")
        if cursor_env_key and not _config_instance.cursor_api.api_key:
            # Force set the API key if it exists in environment but wasn't loaded into config
            _config_instance.cursor_api.api_key = cursor_env_key

        # Ensure Codex/OpenAI agent provider config has an API key; prefer OPENAI_API_KEY
        codex_env_key = os.getenv("OPENAI_API_KEY", "")
        if codex_env_key and not _config_instance.codex_api.api_key:
            _config_instance.codex_api.api_key = codex_env_key

        # Ensure Claude Code config has an API key from ANTHROPIC_API_KEY
        anthropic_env_key = os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_env_key and not _config_instance.claude_code.api_key:
            _config_instance.claude_code.api_key = anthropic_env_key
        
        # Verify embedding provider was loaded - force set from environment if needed
        env_provider = os.getenv("EMBEDDING_PROVIDER", "").lower()
        if env_provider and _config_instance.embedding.provider.lower() == "openai":
            # Force set the provider if environment has it but config doesn't
            _config_instance.embedding.provider = env_provider
        # #region agent log
        try:
            with open(r'c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({"runId":"init","hypothesisId":"F","location":"config.py:129","message":"Config instance created","data":{},"timestamp":__import__('time').time()*1000})+'\n')
        except: pass
        # #endregion
    return _config_instance

# Create a config object that loads lazily and safely
class _LazyConfig:
    """Lazy config wrapper that loads .env only when accessed (outside sandbox)."""
    def __getattr__(self, name):
        return getattr(_get_config_instance(), name)

config = _LazyConfig()

