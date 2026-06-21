"""Preview port allocation and worktree search roots."""
import os
import time
from pathlib import Path

from dashboard.backend.services.preview_detection_service import (
    PreviewDetectionService,
    _PREFERRED_PREVIEW_PORT_RANGE,
    _RESERVED_PREVIEW_PORTS,
)


def test_reserved_ports_exclude_dashboard() -> None:
    assert 5173 in _RESERVED_PREVIEW_PORTS
    assert 8001 in _RESERVED_PREVIEW_PORTS
    assert all(port not in _RESERVED_PREVIEW_PORTS for port in _PREFERRED_PREVIEW_PORT_RANGE)


def test_preview_search_roots_include_worktrees(tmp_path) -> None:
    service = PreviewDetectionService()
    project_id = 42
    worktree_base = tmp_path / ".midnight" / "worktrees" / str(project_id)
    run_a = worktree_base / "100"
    run_b = worktree_base / "101"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)
    roots = service._preview_search_roots(tmp_path, project_id)
    assert tmp_path in roots
    assert run_a in roots or run_b in roots


def test_allocate_preview_launch_never_uses_5173(tmp_path) -> None:
    service = PreviewDetectionService()
    package_root = tmp_path / "frontend"
    package_root.mkdir()
    (package_root / "vite.config.ts").write_text("export default {}", encoding="utf-8")
    launch = service.allocate_preview_launch(
        preview_command="npm run dev",
        package_root=package_root,
        framework="vite",
        script_name="dev",
    )
    port = launch["allocated_port"]
    assert port not in _RESERVED_PREVIEW_PORTS
    assert port >= 5180
    assert ":5173" not in launch["preview_url"]


def test_find_next_free_port_skips_reserved_and_busy(tmp_path, monkeypatch) -> None:
    service = PreviewDetectionService()
    blocked = {5181, 5182}

    def fake_free(port: int) -> bool:
        return port not in blocked and port not in _RESERVED_PREVIEW_PORTS

    monkeypatch.setattr(service, "_port_is_free", fake_free)
    assert service.find_next_free_port(5181) == 5183


def test_resolve_preview_workspace_prefers_newest_worktree(tmp_path) -> None:
    service = PreviewDetectionService()
    project_id = 8
    root = tmp_path / "repo"
    root.mkdir()
    older = root / ".midnight" / "worktrees" / str(project_id) / "50"
    newer = root / ".midnight" / "worktrees" / str(project_id) / "51"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "package.json").write_text('{"name":"old","scripts":{"dev":"vite"}}', encoding="utf-8")
    (newer / "package.json").write_text('{"name":"new","scripts":{"dev":"vite"}}', encoding="utf-8")
    time.sleep(0.01)
    os.utime(newer, None)
    resolved = service.resolve_preview_workspace(str(root), project_id)
    assert resolved.name == "51"


def test_allocate_uses_configured_port_from_package_script(tmp_path) -> None:
    service = PreviewDetectionService()
    package_root = tmp_path / "app"
    package_root.mkdir()
    (package_root / "package.json").write_text(
        '{"name":"app","scripts":{"dev":"vite --port 5190"}}',
        encoding="utf-8",
    )
    launch = service.allocate_preview_launch(
        preview_command="npm run dev",
        package_root=package_root,
        framework="vite",
        script_name="dev",
    )
    assert launch["configured_port"] == 5190
    assert launch["allocated_port"] == 5190
    assert "--port 5190" in launch["preview_command"] or "5190" in launch["preview_command"]
