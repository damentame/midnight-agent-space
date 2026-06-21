"""Build explicit execution batches for concurrent task runs."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


def build_execution_batches(
    planned_tasks: List[Dict[str, Any]],
    *,
    section_max_concurrency: int = 4,
) -> List[Dict[str, Any]]:
    """Return ordered execution batches decided at serialize time."""
    batches: List[Dict[str, Any]] = []
    index = 0
    batch_index = 0
    while index < len(planned_tasks):
        task = planned_tasks[index]
        task_data = task.get("task_data") if isinstance(task.get("task_data"), dict) else {}
        if task_data.get("parallel_group") == "sections" and task_data.get("parallel_safe"):
            section_tasks: List[Dict[str, Any]] = []
            while index < len(planned_tasks):
                current = planned_tasks[index]
                current_data = current.get("task_data") if isinstance(current.get("task_data"), dict) else {}
                if not (
                    current_data.get("parallel_group") == "sections"
                    and current_data.get("parallel_safe")
                ):
                    break
                section_tasks.append(
                    {
                        "task_name": current.get("task_name"),
                        "task_type": current.get("task_type"),
                        "design_section_slug": current_data.get("design_section_slug"),
                        "design_section_order": current_data.get("design_section_order"),
                    }
                )
                index += 1
            batches.append(
                {
                    "batch_index": batch_index,
                    "mode": "parallel",
                    "parallel_group": "sections",
                    "max_concurrency": max(1, section_max_concurrency),
                    "tasks": section_tasks,
                    "label": f"Implement {len(section_tasks)} sections in parallel",
                }
            )
            batch_index += 1
            continue

        batches.append(
            {
                "batch_index": batch_index,
                "mode": "sequential",
                "max_concurrency": 1,
                "tasks": [
                    {
                        "task_name": task.get("task_name"),
                        "task_type": task.get("task_type"),
                    }
                ],
                "label": str(task.get("task_name") or "Task"),
            }
        )
        index += 1
        batch_index += 1
    return batches


def annotate_task_execution_fields(
    task: Dict[str, Any],
    *,
    sequence_index: int,
    execution_batches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge serialize-time execution metadata into persisted task_data."""
    planned = dict(task.get("task_data") or {}) if isinstance(task.get("task_data"), dict) else {}
    batch_index = None
    batch_mode = "sequential"
    max_concurrency = 1
    batch_label = str(task.get("task_name") or "")

    task_name = str(task.get("task_name") or "")
    for batch in execution_batches:
        names = [str(item.get("task_name") or "") for item in batch.get("tasks") or []]
        if task_name in names:
            batch_index = batch.get("batch_index")
            batch_mode = str(batch.get("mode") or "sequential")
            max_concurrency = int(batch.get("max_concurrency") or 1)
            batch_label = str(batch.get("label") or batch_label)
            break

    planned.update(
        {
            "sequence_index": sequence_index,
            "execution_mode": batch_mode,
            "execution_batch_index": batch_index,
            "execution_batch_label": batch_label,
            "execution_max_concurrency": max_concurrency,
        }
    )
    return planned


def _section_label(task: Dict[str, Any]) -> str:
    task_data = task.get("task_data") if isinstance(task.get("task_data"), dict) else {}
    slug = task_data.get("design_section_slug")
    if slug:
        return str(slug).replace("-", " ").replace("_", " ").title()
    return str(task.get("task_name") or "Section")


def assign_milestones(
    planned_tasks: List[Dict[str, Any]],
    *,
    has_figma_import: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Group planned tasks into rule-based milestones for progressive delivery.

    Mutates each task's `task_data` with `milestone_index`/`milestone_name` and returns
    `(planned_tasks, milestones_summary)` where milestones_summary entries have
    `index`, `name`, `task_count`, and `percent_target` (cumulative completion target).
    """
    foundation_types = {"analysis", "planning", "scaffold"}
    review_types = {"review"}

    foundation: List[int] = []
    build: List[int] = []
    polish: List[int] = []
    for idx, task in enumerate(planned_tasks):
        ttype = str(task.get("task_type") or "").lower()
        name = str(task.get("task_name") or "").lower()
        if ttype in foundation_types:
            foundation.append(idx)
        elif ttype in review_types or "integrate" in name:
            polish.append(idx)
        else:
            build.append(idx)

    build_groups: List[List[int]] = []
    if build:
        group_count = min(3, len(build))
        chunk = math.ceil(len(build) / group_count)
        for i in range(0, len(build), chunk):
            build_groups.append(build[i : i + chunk])

    groups: List[List[int]] = []
    milestones: List[Dict[str, Any]] = []

    if foundation:
        groups.append(foundation)
        milestones.append({"name": "Foundation & Skeleton"})

    for i, group in enumerate(build_groups):
        groups.append(group)
        if len(build_groups) == 1:
            name = "Build"
        elif has_figma_import:
            first_label = _section_label(planned_tasks[group[0]])
            last_label = _section_label(planned_tasks[group[-1]])
            name = f"Build: {first_label}" if first_label == last_label else f"Build: {first_label} & {last_label}"
        else:
            name = f"Build: Part {i + 1}"
        milestones.append({"name": name})

    if polish:
        groups.append(polish)
        milestones.append({"name": "Polish, Review & Preview"})

    total = len(milestones)
    for milestone_index, (group, milestone) in enumerate(zip(groups, milestones)):
        milestone["index"] = milestone_index
        milestone["task_count"] = len(group)
        milestone["percent_target"] = round((milestone_index + 1) / total * 100) if total else 0
        for task_idx in group:
            task = planned_tasks[task_idx]
            task_data = task.get("task_data")
            if not isinstance(task_data, dict):
                task_data = {}
                task["task_data"] = task_data
            task_data["milestone_index"] = milestone_index
            task_data["milestone_name"] = milestone["name"]

    return planned_tasks, milestones
