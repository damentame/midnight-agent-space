"""Tests for task-scoped context compaction budgets."""
from dashboard.backend.services.context_pack_service import ContextPackService


def test_task_context_limits_implementation_smaller_than_run_level() -> None:
    service = ContextPackService()
    impl = service._task_context_limits({"task_type": "implementation", "task_name": "Implement section 1: navbar"})
    run_level = service._task_context_limits(None)
    assert impl["max_documents"] <= run_level["max_documents"]
    assert impl["preview_chars"] <= run_level["preview_chars"]


def test_compact_diff_context_shapes_files() -> None:
    service = ContextPackService()
    compact = service.compact_diff_context(
        {
            "summary": "2 files changed",
            "changed_file_count": 2,
            "files": [{"path": "index.html", "status": "modified", "additions": 10, "deletions": 2}],
        }
    )
    assert compact["diff_only"] is True
    assert compact["changed_files"][0]["path"] == "index.html"
