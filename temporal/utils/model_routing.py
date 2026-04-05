"""Resolve LLM model IDs for task execution from execute_mode and optional task metadata."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# task_type values (from generated tasks / DB) that warrant a more capable model
TASK_TYPES_FAVOR_COMPLEX = frozenset({"research", "migration", "design"})
# Narrow / mechanical categories that can use a quicker model when workflow is in complex mode
TASK_TYPES_FAVOR_FAST = frozenset({"documentation"})


def infer_execution_complexity(
    task: Optional[Dict[str, Any]],
    workflow_execute_mode: str,
) -> str:
    """
    Per-task execution complexity for model selection: "fast" or "complex".

    Order:
    1. Explicit task_data.execution_complexity (or top-level) if "fast" or "complex".
    2. Else task_type heuristics (research/migration/design -> complex; documentation -> fast).
    3. Else workflow execute_mode (fast or complex).
    """
    if task:
        td = task.get("task_data")
        if not isinstance(td, dict):
            td = {}
        raw = td.get("execution_complexity") or task.get("execution_complexity")
        if isinstance(raw, str):
            s = raw.strip().lower()
            if s in ("fast", "complex"):
                return s

    mode = (workflow_execute_mode or "fast").lower()
    if mode not in ("fast", "complex"):
        mode = "fast"

    ttype = ""
    if task:
        raw = task.get("task_type")
        if raw is not None:
            ttype = str(raw).strip().lower()

    if ttype in TASK_TYPES_FAVOR_COMPLEX:
        return "complex"
    if ttype in TASK_TYPES_FAVOR_FAST:
        return "fast"
    return mode


def effective_batch_chain_execute_mode(
    peeked_tasks: List[Dict[str, Any]],
    workflow_execute_mode: str,
) -> str:
    """
    When batch mode uses a single Cursor agent + follow-ups, one model applies to the chain.
    Use complex if the workflow is already complex OR any peeked task requires complex.
    """
    if (workflow_execute_mode or "fast").lower() == "complex":
        return "complex"
    for t in peeked_tasks:
        if infer_execution_complexity(t, workflow_execute_mode) == "complex":
            return "complex"
    return "fast"


def resolve_executor_model(
    execute_mode: str,
    agent_provider: str,
    task: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Model ID for the given provider and execute_mode.

    * Codex: always returns a string (falls back to CODEX_MODEL).
    * Claude Code: always returns a string (falls back to CLAUDE_CODE_MODEL).
    * Cursor: may return None when tier env vars are unset so the request
      omits prompt.model and Cursor applies the account/team default.
    """
    from temporal.config import config

    mode = infer_execution_complexity(task, execute_mode)

    provider = (agent_provider or "cursor").lower()
    if provider == "codex":
        c = config.codex_api
        if mode == "complex":
            return (c.model_complex or c.model).strip() or c.model
        return (c.model_fast or c.model).strip() or c.model

    if provider == "claude-code":
        c = config.claude_code
        if mode == "complex":
            return (c.model_complex or c.model).strip() or c.model
        return (c.model_fast or c.model).strip() or c.model

    # Cursor (default)
    c = config.cursor_api
    if mode == "complex":
        s = (c.model_complex or "").strip()
        return s if s else None
    s = (c.model_fast or "").strip()
    return s if s else None


def resolve_serialization_model(execute_mode: str) -> Optional[str]:
    """Optional model for document serialization / task-generation Cursor agents."""
    return resolve_executor_model(execute_mode, "cursor", task=None)
