"""Project refresh metadata helpers."""
from dashboard.backend.services.project_refresh_service import ProjectRefreshService


def test_version_history_reads_metadata_list() -> None:
    metadata = {
        "metadata": {
            "project_version_history": [
                {"version": 1, "git_tag": "mas-v1", "reason": "initial"},
                {"version": 2, "git_tag": "mas-v2", "reason": "retry"},
            ],
        },
    }
    history = ProjectRefreshService._version_history(metadata)
    assert len(history) == 2
    assert history[1]["git_tag"] == "mas-v2"


def test_version_history_empty_when_missing() -> None:
    assert ProjectRefreshService._version_history({}) == []
    assert ProjectRefreshService._version_history({"metadata": "bad"}) == []
