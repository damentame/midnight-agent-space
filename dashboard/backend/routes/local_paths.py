import os
import string
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()


def _safe_resolve(raw_path: str | None) -> Path:
    if raw_path and raw_path.strip():
        return Path(raw_path).expanduser().resolve()
    documents = Path.home() / "Documents"
    return documents.resolve() if documents.exists() else Path.home().resolve()


def _drives() -> list[str]:
    if os.name != "nt":
        return ["/"]
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if Path(drive).exists():
            drives.append(drive)
    return drives


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _find_git_repos(path: Path, max_depth: int = 4, limit: int = 25) -> list[dict[str, str]]:
    repos: list[dict[str, str]] = []

    def visit(current: Path, depth: int) -> None:
        if len(repos) >= limit or depth > max_depth:
            return
        try:
            if _is_git_repo(current):
                repos.append({"name": current.name, "path": str(current)})
                return
            children = [child for child in current.iterdir() if child.is_dir()]
        except (OSError, PermissionError):
            return
        for child in sorted(children, key=lambda item: item.name.lower()):
            if child.name in {".midnight", "node_modules", ".venv", "__pycache__"}:
                continue
            visit(child, depth + 1)

    visit(path, 0)
    return repos


@router.get("/local-paths/browse")
async def browse_local_paths(path: str | None = Query(default=None)):
    current = _safe_resolve(path)
    if not current.exists() or not current.is_dir():
        current = _safe_resolve(None)

    folders = []
    try:
        children = sorted(
            [child for child in current.iterdir() if child.is_dir()],
            key=lambda child: child.name.lower(),
        )
    except (OSError, PermissionError):
        children = []

    for child in children:
        try:
            folders.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_git_repo": _is_git_repo(child),
                }
            )
        except OSError:
            continue

    parent = current.parent if current.parent != current else None
    return {
        "current_path": str(current),
        "parent_path": str(parent) if parent else None,
        "home_path": str(Path.home()),
        "drives": _drives(),
        "is_git_repo": _is_git_repo(current),
        "git_repos": _find_git_repos(current),
        "folders": folders,
    }
