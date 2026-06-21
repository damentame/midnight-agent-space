"""Agent effort estimates for tasks (model/compute cost routing, not human time)."""
from __future__ import annotations

from typing import Any, Dict, Optional

AGENT_EFFORT_LEVELS = ("low", "medium", "high")

_TASK_TYPE_BASE_SCORE: Dict[str, int] = {
    "analysis": 2,
    "planning": 3,
    "documentation": 2,
    "review": 2,
    "implementation": 4,
    "research": 5,
    "migration": 5,
    "design": 4,
    "testing": 3,
    "refactor": 4,
}

_HIGH_EFFORT_KEYWORDS = (
    "architect",
    "migration",
    "refactor entire",
    "multi-file",
    "cross-cutting",
    "security audit",
    "performance",
    "complex",
    "figma",
    "design system",
    "integration",
    "orchestrat",
)

_LOW_EFFORT_KEYWORDS = (
    "summarize",
    "summary",
    "lint",
    "typo",
    "comment",
    "readme",
    "checklist",
    "verify",
    "preview",
    "status",
)


def _clamp_score(score: int) -> int:
    return max(1, min(5, score))


def _score_to_level(score: int) -> str:
    if score <= 2:
        return "low"
    if score <= 3:
        return "medium"
    return "high"


def effort_to_execution_complexity(level: str, task_type: str = "") -> str:
    """Map agent effort tier to fast/complex model bucket."""
    normalized = (level or "medium").strip().lower()
    ttype = (task_type or "").strip().lower()
    if normalized == "high":
        return "complex"
    if normalized == "low":
        return "fast"
    if ttype in {"implementation", "migration", "research", "design", "refactor"}:
        return "complex"
    return "fast"


def estimate_agent_effort(
    *,
    task_name: str,
    task_type: Optional[str] = None,
    description: Optional[str] = None,
    task_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Estimate agent effort on a 1–5 scale and low/medium/high band.
    Uses task type, description heuristics, and any explicit overrides in task_data.
    """
    td = task_data if isinstance(task_data, dict) else {}
    existing = td.get("agent_effort")
    if isinstance(existing, dict) and existing.get("level") in AGENT_EFFORT_LEVELS:
        level = str(existing["level"])
        score = int(existing.get("score") or _clamp_score({"low": 2, "medium": 3, "high": 5}[level]))
        rationale = str(existing.get("rationale") or "Using preset agent effort from task data.")
        return {
            "level": level,
            "score": _clamp_score(score),
            "rationale": rationale,
            "execution_complexity": effort_to_execution_complexity(level, task_type or ""),
        }

    ttype = (task_type or "").strip().lower()
    score = _TASK_TYPE_BASE_SCORE.get(ttype, 3)
    text = f"{task_name} {description or ''}".lower()

    for keyword in _HIGH_EFFORT_KEYWORDS:
        if keyword in text:
            score += 1
            break
    for keyword in _LOW_EFFORT_KEYWORDS:
        if keyword in text:
            score -= 1
            break

    if len(text) > 400:
        score += 1
    elif len(text) < 80:
        score -= 1

    score = _clamp_score(score)
    level = _score_to_level(score)
    rationale = (
        f"Agent effort {level} ({score}/5) from task type '{ttype or 'general'}' "
        f"and scoped description length ({len(text)} chars)."
    )
    return {
        "level": level,
        "score": score,
        "rationale": rationale,
        "execution_complexity": effort_to_execution_complexity(level, ttype),
    }


def enrich_task_with_agent_effort(task: Dict[str, Any]) -> Dict[str, Any]:
    """Return task dict with agent_effort embedded in task_data."""
    effort = estimate_agent_effort(
        task_name=str(task.get("task_name") or "Task"),
        task_type=task.get("task_type"),
        description=task.get("description"),
        task_data=task.get("task_data") if isinstance(task.get("task_data"), dict) else None,
    )
    td = task.get("task_data")
    if not isinstance(td, dict):
        td = {}
    merged = {**task, "task_data": {**td, "agent_effort": effort, "execution_complexity": effort["execution_complexity"]}}
    merged["agent_effort"] = effort
    return merged
