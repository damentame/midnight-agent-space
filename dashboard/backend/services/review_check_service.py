from __future__ import annotations

from typing import Any, Dict, List


class ReviewCheckService:
    """
    Deterministic post-run checks for demo visibility.
    """

    def build_review(
        self,
        *,
        run_status: str,
        execution_result: Dict[str, Any],
        diff_summary: Dict[str, Any],
        artifact_count: int,
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []

        checks.append(
            {
                "check": "run_status_terminal",
                "ok": run_status in {"COMPLETED", "FAILED", "CANCELLED", "PLANNED", "BLOCKED"},
                "value": run_status,
            }
        )
        checks.append(
            {
                "check": "process_exit_zero",
                "ok": execution_result.get("exit_code") in (None, 0),
                "value": execution_result.get("exit_code"),
            }
        )
        checks.append(
            {
                "check": "timeout_not_triggered",
                "ok": not bool(execution_result.get("timed_out")),
                "value": bool(execution_result.get("timed_out")),
            }
        )
        checks.append(
            {
                "check": "artifacts_captured",
                "ok": artifact_count > 0,
                "value": artifact_count,
            }
        )
        checks.append(
            {
                "check": "git_changes_recorded",
                "ok": int(diff_summary.get("inserted", 0)) >= 0,
                "value": int(diff_summary.get("inserted", 0)),
            }
        )

        all_ok = all(bool(check.get("ok")) for check in checks)
        return {"ok": all_ok, "checks": checks}


review_check_service = ReviewCheckService()
