"""Next.js monorepo preview detection."""
import json
from pathlib import Path

from dashboard.backend.services.preview_detection_service import PreviewDetectionService


def test_monorepo_detects_next_via_frontend_prefix(tmp_path) -> None:
    service = PreviewDetectionService()
    root = tmp_path / "app"
    root.mkdir()
    frontend = root / "frontend"
    frontend.mkdir()
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "monorepo",
                "scripts": {"dev": "concurrently npm run dev:api npm run dev:web", "dev:web": "npm run dev --prefix frontend"},
                "devDependencies": {"concurrently": "^8.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "name": "web",
                "scripts": {"dev": "next dev -p 3000"},
                "dependencies": {"next": "^14.0.0", "react": "^18.0.0"},
            }
        ),
        encoding="utf-8",
    )

    detected = service._detect_from_package_json(root, json.loads((root / "package.json").read_text()))
    assert detected["ok"] is True
    assert detected["framework"] == "next"
    assert "frontend" in detected["preview_command"]
    assert ":5173" not in detected["preview_url"]


def test_infer_framework_finds_next_in_frontend_subpackage(tmp_path) -> None:
    service = PreviewDetectionService()
    root = tmp_path / "app"
    root.mkdir()
    frontend = root / "frontend"
    frontend.mkdir()
    root_pkg = {"name": "root", "dependencies": {}}
    (frontend / "package.json").write_text(
        json.dumps({"dependencies": {"next": "^14.0.0"}}),
        encoding="utf-8",
    )
    assert service._infer_framework(root, root_pkg) == "next"
