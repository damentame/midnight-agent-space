"""CLI model selection for dashboard quick-runs (cost-aware routing)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import app_config
from .agent_effort_service import AGENT_EFFORT_LEVELS, enrich_task_with_agent_effort, estimate_agent_effort

MODEL_SELECTION_OPTIMIZED = "optimized"
MODEL_SELECTION_FIXED = "fixed"


def _provider_key(runtime_provider: str) -> str:
    if runtime_provider == "claude-cli":
        return "claude-cli"
    if runtime_provider == "cursor-agent":
        return "cursor-agent"
    return "codex-cli"


def default_models_for_provider(runtime_provider: str) -> Dict[str, str]:
    if runtime_provider == "claude-cli":
        fast = app_config.claude_cli_model_fast or "haiku"
        complex_model = app_config.claude_cli_model_complex or app_config.claude_cli_model or "sonnet"
        return {"fast": fast, "complex": complex_model, "default": app_config.claude_cli_model or complex_model}
    if runtime_provider == "cursor-agent":
        fast = app_config.cursor_agent_model_fast or app_config.cursor_agent_model or "composer-2.5"
        complex_model = app_config.cursor_agent_model_complex or app_config.cursor_agent_model or fast
        return {"fast": fast, "complex": complex_model, "default": app_config.cursor_agent_model or complex_model}
    fast = app_config.codex_cli_model_fast or "gpt-4.1-mini"
    complex_model = app_config.codex_cli_model_complex or app_config.codex_cli_model or "gpt-4.1"
    return {"fast": fast, "complex": complex_model, "default": app_config.codex_cli_model or complex_model}


def model_catalog() -> Dict[str, Any]:
    codex = default_models_for_provider("codex-cli")
    claude = default_models_for_provider("claude-cli")
    cursor = default_models_for_provider("cursor-agent")
    return {
        "selection_modes": [
            {
                "id": MODEL_SELECTION_OPTIMIZED,
                "label": "Balanced agent usage",
                "description": (
                    "Route code tasks to Cursor Agent, review tasks to your reviewer CLI, "
                    "and match model cost to per-task agent effort."
                ),
            },
            {"id": MODEL_SELECTION_FIXED, "label": "Fixed model", "description": "Use one runtime/model for every task in the run."},
        ],
        "providers": {
            "codex-cli": {
                "label": "Codex CLI",
                "optimized": codex,
                "suggested_models": sorted({codex["fast"], codex["complex"], codex["default"]}),
            },
            "claude-cli": {
                "label": "Claude CLI",
                "optimized": claude,
                "suggested_models": ["haiku", "sonnet", "opus"],
            },
            "cursor-agent": {
                "label": "Cursor Agent",
                "optimized": cursor,
                "suggested_models": sorted({cursor["fast"], cursor["complex"], cursor["default"]}),
            },
        },
        "agent_effort_levels": list(AGENT_EFFORT_LEVELS),
    }


def resolve_cli_model(
    *,
    runtime_provider: str,
    selection_mode: str,
    fixed_model: Optional[str],
    task: Optional[Dict[str, Any]] = None,
) -> str:
    tiers = default_models_for_provider(runtime_provider)
    mode = (selection_mode or MODEL_SELECTION_OPTIMIZED).strip().lower()
    if mode == MODEL_SELECTION_FIXED:
        chosen = (fixed_model or "").strip()
        if chosen:
            return chosen
        return tiers["default"]

    complexity = "fast"
    if task:
        enriched = enrich_task_with_agent_effort(task)
        effort = enriched.get("agent_effort") or {}
        complexity = str(effort.get("execution_complexity") or "fast")
        td = task.get("task_data")
        if isinstance(td, dict) and td.get("execution_complexity"):
            complexity = str(td["execution_complexity"])

    if complexity == "complex":
        return tiers["complex"]
    return tiers["fast"]


def build_task_model_plan(
    *,
    runtime_provider: str,
    selection_mode: str,
    fixed_model: Optional[str],
    tasks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for task in tasks:
        enriched = enrich_task_with_agent_effort(task)
        effort = enriched.get("agent_effort") or {}
        model = resolve_cli_model(
            runtime_provider=runtime_provider,
            selection_mode=selection_mode,
            fixed_model=fixed_model,
            task=enriched,
        )
        plan.append(
            {
                "task_id": enriched.get("task_id"),
                "task_name": enriched.get("task_name"),
                "task_type": enriched.get("task_type"),
                "agent_effort": effort,
                "model": model,
                "selection_mode": selection_mode,
            }
        )
    return plan
