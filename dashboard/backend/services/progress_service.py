"""Rule-based progress/PM summary for a project. No LLM calls."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ..database import DatabaseManager
from .schema_support import schema_support

_COMPLETED_STATUSES = frozenset({"COMPLETED", "DONE", "PASSED"})
_FAILED_STATUSES = frozenset({"FAILED"})
_RUNNING_STATUSES = frozenset({"RUNNING"})
_STALE_RUNNING_MINUTES = 20


class ProgressService:
    async def _project_tasks(self, db: DatabaseManager, project_id: int) -> List[Dict[str, Any]]:
        if not await schema_support.table_exists(db, "task"):
            return []
        rows = await db.fetch_many(
            """
            SELECT task_id, task_name, task_type, description, status, priority,
                   task_data, created_at, updated_at
            FROM main.task
            WHERE project_id = $1
              AND COALESCE(status, '') NOT IN ('SUPERSEDED')
            ORDER BY COALESCE(priority, 999999), task_id
            """,
            project_id,
        )
        out: List[Dict[str, Any]] = []
        for row in rows:
            task = dict(row)
            task_data = task.get("task_data")
            if isinstance(task_data, str):
                try:
                    task_data = json.loads(task_data)
                except json.JSONDecodeError:
                    task_data = {}
            task["task_data"] = task_data if isinstance(task_data, dict) else {}
            out.append(task)
        return out

    async def compute_progress(self, db: DatabaseManager, project_id: int) -> Dict[str, Any]:
        tasks = await self._project_tasks(db, project_id)

        milestone_map: Dict[int, Dict[str, Any]] = {}
        unassigned: List[Dict[str, Any]] = []
        for task in tasks:
            task_data = task.get("task_data") or {}
            milestone_index = task_data.get("milestone_index")
            if milestone_index is None:
                unassigned.append(task)
                continue
            index = int(milestone_index)
            entry = milestone_map.setdefault(
                index,
                {
                    "index": index,
                    "name": task_data.get("milestone_name") or f"Milestone {index}",
                    "tasks": [],
                },
            )
            entry["tasks"].append(task)

        if unassigned:
            if milestone_map:
                last_index = max(milestone_map.keys())
                milestone_map[last_index]["tasks"].extend(unassigned)
            else:
                milestone_map[0] = {"index": 0, "name": "Build", "tasks": unassigned}

        milestones: List[Dict[str, Any]] = []
        completed_tasks: List[Dict[str, Any]] = []
        in_progress_tasks: List[Dict[str, Any]] = []
        pending_tasks: List[Dict[str, Any]] = []
        risks: List[str] = []

        now = datetime.now(timezone.utc)
        total_tasks = len(tasks)
        total_completed = 0
        milestone_count = len(milestone_map) or 1

        for index in sorted(milestone_map.keys()):
            entry = milestone_map[index]
            m_tasks = entry["tasks"]
            m_completed = 0
            for task in m_tasks:
                status = str(task.get("status") or "").upper()
                summary = {
                    "task_id": task.get("task_id"),
                    "task_name": task.get("task_name"),
                    "milestone_name": entry["name"],
                    "status": status,
                }
                if status in _COMPLETED_STATUSES:
                    m_completed += 1
                    completed_tasks.append(summary)
                elif status in _RUNNING_STATUSES:
                    in_progress_tasks.append(summary)
                else:
                    pending_tasks.append(summary)

                if status in _FAILED_STATUSES:
                    risks.append(f"Task '{task.get('task_name')}' ({entry['name']}) failed.")
                elif status in _RUNNING_STATUSES:
                    updated_at = task.get("updated_at")
                    if isinstance(updated_at, datetime):
                        updated = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
                        if now - updated > timedelta(minutes=_STALE_RUNNING_MINUTES):
                            risks.append(
                                f"Task '{task.get('task_name')}' ({entry['name']}) has been RUNNING for "
                                f"over {_STALE_RUNNING_MINUTES} minutes — may be stuck."
                            )
                else:
                    agent_effort = task.get("task_data", {}).get("agent_effort") or {}
                    if str(agent_effort.get("level") or "").lower() == "high":
                        risks.append(
                            f"High-effort task '{task.get('task_name')}' ({entry['name']}) not yet started."
                        )

            total_completed += m_completed
            if m_completed == 0:
                m_status = "pending"
            elif m_completed == len(m_tasks):
                m_status = "completed"
            else:
                m_status = "in_progress"

            milestones.append(
                {
                    "index": index,
                    "name": entry["name"],
                    "status": m_status,
                    "task_count": len(m_tasks),
                    "completed_count": m_completed,
                    "percent_target": round((index + 1) / milestone_count * 100),
                }
            )

        percent_complete = round(100 * total_completed / total_tasks) if total_tasks else 0

        return {
            "percent_complete": percent_complete,
            "total_tasks": total_tasks,
            "completed_task_count": total_completed,
            "milestones": milestones,
            "completed_tasks": completed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "pending_tasks": pending_tasks,
            "risks": risks,
            "generated_at": now.isoformat(),
        }

    def render_markdown(self, progress: Dict[str, Any]) -> str:
        percent = int(progress.get("percent_complete") or 0)
        filled = round(percent / 10)
        bar = "#" * filled + "-" * (10 - filled)
        lines = [
            "# Progress",
            "",
            f"Overall: [{bar}] {percent}% "
            f"({progress.get('completed_task_count', 0)}/{progress.get('total_tasks', 0)} tasks)",
            "",
            "## Milestones",
        ]
        icons = {"completed": "[x]", "in_progress": "[~]", "pending": "[ ]"}
        for milestone in progress.get("milestones") or []:
            icon = icons.get(str(milestone.get("status")), "[ ]")
            lines.append(
                f"- {icon} {milestone.get('name')} — "
                f"{milestone.get('completed_count')}/{milestone.get('task_count')} tasks "
                f"(target {milestone.get('percent_target')}%)"
            )
        risks = progress.get("risks") or []
        if risks:
            lines.append("")
            lines.append("## Risks")
            for risk in risks:
                lines.append(f"- {risk}")
        lines.append("")
        lines.append(f"_Generated at {progress.get('generated_at')}_")
        return "\n".join(lines)


progress_service = ProgressService()
