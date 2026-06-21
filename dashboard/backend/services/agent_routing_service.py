"""Route tasks to Cursor Agent (code), Codex/Claude CLI (review), or a single primary runtime."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .agent_effort_service import enrich_task_with_agent_effort
from .model_routing_service import MODEL_SELECTION_OPTIMIZED, resolve_cli_model

EXECUTABLE_CLI_PROVIDERS = frozenset({"codex-cli", "claude-cli", "cursor-agent"})
REVIEW_CLI_PROVIDERS = frozenset({"codex-cli", "claude-cli"})

CODE_TASK_TYPES = frozenset(
    {
        "analysis",
        "implementation",
        "refactor",
        "migration",
        "testing",
        "design",
        "planning",
    }
)
REVIEW_TASK_TYPES = frozenset({"review"})

_CODE_NAME_HINTS = (
    "implement",
    "refactor",
    "build",
    "code",
    "frontend",
    "backend",
    "component",
    "api",
    "serialize",
    "preview",
    "worktree",
)
_REVIEW_NAME_HINTS = ("review", "quality", "audit", "verify design", "design adherence")


def uses_balanced_agent_routing(model_selection_mode: str) -> bool:
    return (model_selection_mode or MODEL_SELECTION_OPTIMIZED).strip().lower() == MODEL_SELECTION_OPTIMIZED


def resolve_reviewer_provider(
    *,
    primary_provider: str,
    reviewer_provider: Optional[str] = None,
) -> str:
    candidate = (reviewer_provider or "").strip()
    if candidate in REVIEW_CLI_PROVIDERS:
        return candidate
    if primary_provider in REVIEW_CLI_PROVIDERS:
        return primary_provider
    return "claude-cli"


def task_role(task: Dict[str, Any]) -> str:
    ttype = str(task.get("task_type") or "").strip().lower()
    name = str(task.get("task_name") or "").strip().lower()
    description = str(task.get("description") or "").strip().lower()
    text = f"{name} {description}"

    if ttype in REVIEW_TASK_TYPES or any(hint in text for hint in _REVIEW_NAME_HINTS):
        return "review"
    if ttype in CODE_TASK_TYPES or any(hint in text for hint in _CODE_NAME_HINTS):
        return "code"
    return "general"


def resolve_task_runtime_provider(
    task: Dict[str, Any],
    *,
    primary_provider: str,
    reviewer_provider: str,
    balanced: bool,
    cursor_available: bool,
) -> str:
    role = task_role(task)
    if role == "review":
        return reviewer_provider
    if role == "code" and (balanced or primary_provider == "cursor-agent"):
        if cursor_available:
            return "cursor-agent"
        return primary_provider if primary_provider in EXECUTABLE_CLI_PROVIDERS else reviewer_provider
    if primary_provider in EXECUTABLE_CLI_PROVIDERS:
        return primary_provider
    return reviewer_provider


def build_task_agent_plan(
    *,
    primary_provider: str,
    reviewer_provider: str,
    model_selection_mode: str,
    fixed_model: Optional[str],
    tasks: List[Dict[str, Any]],
    cursor_available: bool,
) -> List[Dict[str, Any]]:
    balanced = uses_balanced_agent_routing(model_selection_mode)
    reviewer = resolve_reviewer_provider(
        primary_provider=primary_provider,
        reviewer_provider=reviewer_provider,
    )
    plan: List[Dict[str, Any]] = []
    for task in tasks:
        enriched = enrich_task_with_agent_effort(task)
        runtime_provider = resolve_task_runtime_provider(
            enriched,
            primary_provider=primary_provider,
            reviewer_provider=reviewer,
            balanced=balanced,
            cursor_available=cursor_available,
        )
        model = resolve_cli_model(
            runtime_provider=runtime_provider,
            selection_mode=model_selection_mode,
            fixed_model=fixed_model,
            task=enriched,
        )
        plan.append(
            {
                "task_id": enriched.get("task_id"),
                "task_name": enriched.get("task_name"),
                "task_type": enriched.get("task_type"),
                "task_role": task_role(enriched),
                "runtime_provider": runtime_provider,
                "reviewer_provider": reviewer if runtime_provider != reviewer else None,
                "agent_effort": enriched.get("agent_effort"),
                "model": model,
                "balanced_routing": balanced,
            }
        )
    return plan


def should_run_post_execution_reviewer(
    *,
    task_agent_plan: List[Dict[str, Any]],
    balanced: bool,
) -> bool:
    if balanced:
        return True
    return any(entry.get("runtime_provider") == "cursor-agent" for entry in task_agent_plan)
