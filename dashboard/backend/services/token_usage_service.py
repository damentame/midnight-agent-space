"""Token usage tracking, cost estimation, and efficiency targets for MAS runs."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# USD per 1M tokens (input, output). Approximate catalog prices for budgeting.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "haiku": {"input": 0.25, "output": 1.25},
    "sonnet": {"input": 3.0, "output": 15.0},
    "opus": {"input": 15.0, "output": 75.0},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "composer-2.5": {"input": 2.0, "output": 8.0},
    "default": {"input": 3.0, "output": 15.0},
}

# Completed app-equivalent targets (total tokens).
APP_EQUIVALENT_TARGETS: Dict[str, int] = {
    "minimum_acceptable": 35_000_000,
    "commercial": 25_000_000,
    "excellent": 15_000_000,
    "elite": 10_000_000,
}

# Task-type token budgets (min, max) in tokens.
TASK_TYPE_BUDGETS: Dict[str, Tuple[int, int]] = {
    "bug_fix": (250_000, 1_000_000),
    "medium_feature": (1_000_000, 5_000_000),
    "large_feature": (5_000_000, 12_000_000),
    "full_app": (15_000_000, 25_000_000),
    "large_refactor": (25_000_000, 50_000_000),
}

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: Optional[str]) -> int:
    if not text:
        return 0
    return max(1, len(str(text)) // _CHARS_PER_TOKEN)


def normalize_model_key(model: Optional[str]) -> str:
    value = (model or "").strip().lower()
    if not value:
        return "default"
    for key in MODEL_PRICING:
        if key != "default" and key in value:
            return key
    return "default"


def resolve_task_budget_key(task: Optional[Dict[str, Any]]) -> str:
    if not task:
        return "medium_feature"
    task_type = str(task.get("task_type") or "").lower()
    name = str(task.get("task_name") or "").lower()
    if task_type in {"review", "analysis", "planning"}:
        return "medium_feature"
    if "integrate" in name or "review" in name:
        return "medium_feature"
    if "implement section" in name or task_type == "implementation":
        return "medium_feature"
    if task_type in {"design", "refactor"}:
        return "large_feature"
    if "bug" in name or "fix" in name:
        return "bug_fix"
    if "refactor" in name:
        return "large_refactor"
    task_count_hint = 0
    td = task.get("task_data")
    if isinstance(td, dict):
        task_count_hint = int(td.get("project_task_count") or 0)
    if task_count_hint >= 10:
        return "full_app"
    return "medium_feature"


def task_budget(task: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    key = resolve_task_budget_key(task)
    low, high = TASK_TYPE_BUDGETS.get(key, TASK_TYPE_BUDGETS["medium_feature"])
    return {"key": key, "min_tokens": low, "max_tokens": high}


def compute_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    model: Optional[str] = None,
) -> float:
    pricing = MODEL_PRICING.get(normalize_model_key(model), MODEL_PRICING["default"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 4)


def _coerce_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def extract_usage_from_payload(payload: Any) -> Optional[Dict[str, int]]:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if isinstance(usage, dict):
        inp = _coerce_int(usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("input"))
        out = _coerce_int(usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("output"))
        if inp or out:
            return {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}
    message = payload.get("message")
    if isinstance(message, dict):
        nested = extract_usage_from_payload(message)
        if nested:
            return nested
    return None


def extract_usage_from_cli_streams(
    stdout_tail: Optional[List[str]],
    stderr_tail: Optional[List[str]] = None,
) -> Optional[Dict[str, int]]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    found = False
    for line in list(stdout_tail or []) + list(stderr_tail or []):
        text = str(line).strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            candidates = payload
        else:
            candidates = [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            usage = extract_usage_from_payload(item)
            if usage:
                found = True
                totals["input_tokens"] += usage["input_tokens"]
                totals["output_tokens"] += usage["output_tokens"]
                totals["total_tokens"] += usage["total_tokens"]
    return totals if found else None


def compress_log_lines(lines: Optional[List[str]], *, max_lines: int = 12, max_chars: int = 2400) -> List[str]:
    """Summarize CLI output before sending back to models (tool-call compression)."""
    if not lines:
        return []
    cleaned: List[str] = []
    for raw in lines:
        text = re.sub(r"\s+", " ", str(raw)).strip()
        if not text:
            continue
        if len(text) > 240:
            text = text[:240] + "…"
        cleaned.append(text)
    if len(cleaned) <= max_lines:
        joined = cleaned
    else:
        head = cleaned[:4]
        tail = cleaned[-(max_lines - 5) :]
        joined = head + [f"… ({len(cleaned) - len(head) - len(tail)} lines omitted) …"] + tail
    out: List[str] = []
    total = 0
    for line in joined:
        if total + len(line) > max_chars:
            break
        out.append(line)
        total += len(line)
    return out


class TokenUsageService:
    def build_task_usage_record(
        self,
        *,
        task: Optional[Dict[str, Any]],
        model: str,
        runtime_provider: str,
        prompt: Optional[str],
        cli_result: Dict[str, Any],
        context_chars: int = 0,
    ) -> Dict[str, Any]:
        measured = extract_usage_from_cli_streams(
            cli_result.get("stdout_tail"),
            cli_result.get("stderr_tail"),
        )
        prompt_tokens = estimate_tokens(prompt)
        context_tokens = max(0, context_chars // _CHARS_PER_TOKEN)
        output_estimate = estimate_tokens("\n".join(cli_result.get("stdout_tail") or [])[-8000:])

        if measured:
            input_tokens = measured["input_tokens"] or max(prompt_tokens + context_tokens, prompt_tokens)
            output_tokens = measured["output_tokens"] or output_estimate
            source = "provider"
        else:
            input_tokens = prompt_tokens + context_tokens
            output_tokens = output_estimate
            source = "estimated"

        total_tokens = input_tokens + output_tokens
        budget = task_budget(task)
        cost_usd = compute_cost_usd(input_tokens=input_tokens, output_tokens=output_tokens, model=model)
        over_budget = total_tokens > budget["max_tokens"]

        return {
            "task_id": task.get("task_id") if task else None,
            "task_name": task.get("task_name") if task else None,
            "task_type": task.get("task_type") if task else None,
            "model": model,
            "runtime_provider": runtime_provider,
            "source": source,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "prompt_tokens_estimated": prompt_tokens,
            "context_tokens_estimated": context_tokens,
            "cost_usd": cost_usd,
            "budget": budget,
            "over_budget": over_budget,
            "elapsed_ms": cli_result.get("elapsed_ms"),
            "event_count": cli_result.get("event_count"),
        }

    def aggregate_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
        by_model: Dict[str, Dict[str, Any]] = {}
        by_provider: Dict[str, Dict[str, Any]] = {}
        tasks_over_budget = 0

        for record in records:
            if not isinstance(record, dict):
                continue
            inp = _coerce_int(record.get("input_tokens"))
            out = _coerce_int(record.get("output_tokens"))
            total = _coerce_int(record.get("total_tokens")) or (inp + out)
            cost = float(record.get("cost_usd") or 0.0)
            totals["input_tokens"] += inp
            totals["output_tokens"] += out
            totals["total_tokens"] += total
            totals["cost_usd"] = round(totals["cost_usd"] + cost, 4)
            if record.get("over_budget"):
                tasks_over_budget += 1

            model = str(record.get("model") or "unknown")
            bucket = by_model.setdefault(
                model,
                {"model": model, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "task_count": 0},
            )
            bucket["input_tokens"] += inp
            bucket["output_tokens"] += out
            bucket["total_tokens"] += total
            bucket["cost_usd"] = round(bucket["cost_usd"] + cost, 4)
            bucket["task_count"] += 1

            provider = str(record.get("runtime_provider") or "unknown")
            pb = by_provider.setdefault(
                provider,
                {"runtime_provider": provider, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "task_count": 0},
            )
            pb["input_tokens"] += inp
            pb["output_tokens"] += out
            pb["total_tokens"] += total
            pb["cost_usd"] = round(pb["cost_usd"] + cost, 4)
            pb["task_count"] += 1

        efficiency = self.efficiency_assessment(totals["total_tokens"])
        return {
            "totals": totals,
            "by_model": sorted(by_model.values(), key=lambda row: row["total_tokens"], reverse=True),
            "by_provider": sorted(by_provider.values(), key=lambda row: row["total_tokens"], reverse=True),
            "task_records": records,
            "tasks_over_budget": tasks_over_budget,
            "efficiency": efficiency,
        }

    def efficiency_assessment(self, total_tokens: int) -> Dict[str, Any]:
        commercial = APP_EQUIVALENT_TARGETS["commercial"]
        excellent = APP_EQUIVALENT_TARGETS["excellent"]
        minimum = APP_EQUIVALENT_TARGETS["minimum_acceptable"]
        if total_tokens <= APP_EQUIVALENT_TARGETS["elite"]:
            rating = "elite"
        elif total_tokens <= excellent:
            rating = "excellent"
        elif total_tokens <= commercial:
            rating = "commercial"
        elif total_tokens <= minimum:
            rating = "minimum_acceptable"
        else:
            rating = "over_target"
        improvement_vs_110m = round(max(0.0, 1.0 - (total_tokens / 110_000_000)) * 100, 1)
        return {
            "rating": rating,
            "total_tokens": total_tokens,
            "targets": APP_EQUIVALENT_TARGETS,
            "commercial_target": commercial,
            "excellent_target": excellent,
            "improvement_vs_110m_baseline_pct": improvement_vs_110m,
            "multiplier_to_commercial": round(total_tokens / commercial, 2) if commercial else None,
            "multiplier_to_excellent": round(total_tokens / excellent, 2) if excellent else None,
        }

    async def project_usage_summary(
        self,
        db,
        project_id: int,
        *,
        limit: int = 20,
    ) -> Dict[str, Any]:
        from .schema_support import schema_support

        if not await schema_support.table_exists(db, "agent_run"):
            return {"project_id": project_id, "runs": [], "totals": {"total_tokens": 0, "cost_usd": 0.0}}

        rows = await db.fetch_many(
            """
            SELECT agent_run_id, status, result_payload, created_at, finished_at
            FROM main.agent_run
            WHERE project_id = $1
            ORDER BY agent_run_id DESC
            LIMIT $2
            """,
            project_id,
            limit,
        )
        run_summaries: List[Dict[str, Any]] = []
        all_records: List[Dict[str, Any]] = []
        for row in rows:
            payload = row.get("result_payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            usage = (payload or {}).get("token_usage") if isinstance(payload, dict) else None
            if not usage:
                execution = (payload or {}).get("execution") if isinstance(payload, dict) else None
                usage = (execution or {}).get("token_usage") if isinstance(execution, dict) else None
            if not usage:
                continue
            records = list(usage.get("task_records") or [])
            all_records.extend(records)
            run_summaries.append(
                {
                    "agent_run_id": row.get("agent_run_id"),
                    "status": row.get("status"),
                    "created_at": row.get("created_at"),
                    "finished_at": row.get("finished_at"),
                    "token_usage": usage,
                }
            )

        aggregate = self.aggregate_records(all_records) if all_records else {
            "totals": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
            "by_model": [],
            "by_provider": [],
            "task_records": [],
            "tasks_over_budget": 0,
            "efficiency": self.efficiency_assessment(0),
        }
        return {
            "project_id": project_id,
            "run_count": len(run_summaries),
            "runs": run_summaries,
            **aggregate,
        }

    def run_usage_from_payload(self, result_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(result_payload, dict):
            return None
        usage = result_payload.get("token_usage")
        if isinstance(usage, dict):
            return usage
        execution = result_payload.get("execution")
        if isinstance(execution, dict) and isinstance(execution.get("token_usage"), dict):
            return execution["token_usage"]
        return None


token_usage_service = TokenUsageService()
