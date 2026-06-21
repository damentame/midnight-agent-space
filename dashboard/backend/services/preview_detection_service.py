"""Detect dev-server preview commands and URLs from a project workspace."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .repo_workspace_service import RepoWorkspaceService, slugify_project_name

_PACKAGE_JSON_CANDIDATES = (
    ".",
    "dashboard/frontend",
    "frontend",
    "web",
    "client",
    "app",
    "packages/web",
)

_SCRIPT_PRIORITY = ("dev", "start", "frontend", "dev:frontend", "preview", "serve", "develop")

_DASHBOARD_MARKERS = (
    "midnight agent space",
    "mas-dashboard",
    "midnight-agent-space",
)

# Port 5173 is the Midnight Agent Space dashboard (Vite). Never assign it to project previews.
_RESERVED_PREVIEW_PORTS = frozenset({5173, 8001})
_PREFERRED_PREVIEW_PORT_RANGE = range(5180, 5300)


class PreviewDetectionService:
    def resolve_repo_path(
        self,
        *,
        runtime_preferences: Dict[str, Any],
        project_name: str,
        workspace_service: Optional[RepoWorkspaceService] = None,
    ) -> str:
        prefs = runtime_preferences or {}
        repo_path = str(prefs.get("repo_path") or "").strip()
        if repo_path:
            return repo_path
        parent = str(prefs.get("workspace_parent_path") or "").strip()
        if not parent:
            return ""
        workspace = workspace_service or RepoWorkspaceService()
        slug = slugify_project_name(project_name)
        candidate = Path(parent).expanduser().resolve() / slug
        if candidate.is_dir():
            return str(candidate)
        for suffix_dir in sorted(Path(parent).expanduser().resolve().glob(f"{slug}*")):
            if suffix_dir.is_dir():
                return str(suffix_dir.resolve())
        return str(candidate)

    def resolve_preview_workspace(self, repo_path: str, project_id: Optional[int] = None) -> Path:
        """Prefer the newest agent worktree that contains a runnable app."""
        root = Path(str(repo_path)).expanduser().resolve()
        if project_id is not None:
            worktree_base = root / ".midnight" / "worktrees" / str(project_id)
            if worktree_base.is_dir():
                children = sorted(
                    [path for path in worktree_base.iterdir() if path.is_dir()],
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
                for child in children:
                    if self._has_previewable_app(child):
                        return child
        return root

    @staticmethod
    def _has_previewable_app(root: Path) -> bool:
        return (
            (root / "package.json").is_file()
            or (root / "index.html").is_file()
            or (root / "manage.py").is_file()
        )

    def detect(self, repo_path: str, project_id: Optional[int] = None) -> Dict[str, Any]:
        root = Path(str(repo_path)).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {"ok": False, "error": f"Repo path does not exist: {root}"}

        primary = self.resolve_preview_workspace(repo_path, project_id)
        search_roots = [primary]
        for candidate in self._preview_search_roots(root, project_id):
            if candidate.resolve() not in {item.resolve() for item in search_roots}:
                search_roots.append(candidate)
        errors: List[str] = []
        for search_root in search_roots:
            result = self._detect_in_directory(search_root)
            if result.get("ok"):
                result["search_root"] = str(search_root)
                return result
            if result.get("error"):
                errors.append(f"{search_root}: {result['error']}")
        return {
            "ok": False,
            "error": errors[-1] if errors else "No previewable app found in workspace.",
            "working_directory": str(root),
            "searched_paths": [str(path) for path in search_roots],
        }

    def _preview_search_roots(self, root: Path, project_id: Optional[int]) -> List[Path]:
        roots: List[Path] = [root]
        if project_id is not None:
            worktree_base = root / ".midnight" / "worktrees" / str(project_id)
            if worktree_base.is_dir():
                children = [path for path in worktree_base.iterdir() if path.is_dir()]
                children.sort(key=lambda path: path.stat().st_mtime, reverse=True)
                roots.extend(children)
        deduped: List[Path] = []
        seen: set[str] = set()
        for candidate in roots:
            key = str(candidate.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _detect_in_directory(self, root: Path) -> Dict[str, Any]:
        package_root, package = self._find_package_json(root)
        if package and package_root is not None:
            return self._detect_from_package_json(package_root, package)

        if (root / "manage.py").exists():
            port = self.find_available_port(8000 if 8000 not in _RESERVED_PREVIEW_PORTS else None)
            return {
                "ok": True,
                "framework": "django",
                "preview_command": f"python manage.py runserver {port}",
                "preview_url": f"http://127.0.0.1:{port}",
                "allocated_port": port,
                "port_note": f"Django dev server on port {port}.",
                "working_directory": str(root),
                "source": "manage.py",
            }

        if (root / "index.html").exists():
            port = self.find_available_port(8080 if 8080 not in _RESERVED_PREVIEW_PORTS else None)
            return {
                "ok": True,
                "framework": "static",
                "preview_command": f"python -m http.server {port}",
                "preview_url": f"http://127.0.0.1:{port}",
                "allocated_port": port,
                "port_note": f"Static file server on port {port}.",
                "working_directory": str(root),
                "source": "index.html",
            }

        return {
            "ok": False,
            "error": "No package.json or recognizable app entry found in this folder.",
            "working_directory": str(root),
        }

    def apply_to_runtime_preferences(
        self,
        runtime_preferences: Dict[str, Any],
        *,
        repo_path: str,
        force: bool = False,
        project_id: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        prefs = dict(runtime_preferences or {})
        if not repo_path:
            return prefs, None
        prefs = self._clear_invalid_preview_prefs(prefs)
        if not force and prefs.get("preview_command") and prefs.get("preview_url"):
            return prefs, None
        detected = self.detect(repo_path, project_id)
        if not detected.get("ok"):
            return prefs, detected
        prefs["repo_path"] = repo_path
        prefs["preview_command"] = detected.get("preview_command")
        prefs["preview_url"] = detected.get("preview_url")
        prefs["preview_working_directory"] = detected.get("working_directory")
        prefs["preview_framework"] = detected.get("framework")
        prefs["preview_detected_from"] = detected.get("source")
        return prefs, detected

    @staticmethod
    def _clear_invalid_preview_prefs(prefs: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(prefs)
        preview_url = str(cleaned.get("preview_url") or "")
        uses_dashboard_port = ":5173" in preview_url
        if (cleaned.get("preview_url") and not cleaned.get("preview_command")) or uses_dashboard_port:
            for key in (
                "preview_url",
                "preview_working_directory",
                "preview_framework",
                "preview_detected_from",
                "preview_session",
            ):
                cleaned.pop(key, None)
        return cleaned

    @staticmethod
    def _is_excluded_package(package_root: Path, package: Dict[str, Any]) -> bool:
        name = str(package.get("name") or "").lower()
        if name in {"mas-dashboard", "midnight-agent-space"}:
            return True
        normalized = str(package_root).replace("\\", "/").lower()
        return "midnight-agent-space/dashboard" in normalized

    def _script_score(self, scripts: Dict[str, Any]) -> int:
        score = 0
        for index, name in enumerate(_SCRIPT_PRIORITY):
            if name in scripts:
                score = max(score, 20 - index)
        return score

    def _find_package_json(self, root: Path) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
        skip_dirs = {"node_modules", ".git", ".midnight", "dist", "build", ".venv", "__pycache__"}
        best: Optional[Tuple[Tuple[int, int], Path, Dict[str, Any]]] = None

        def consider(package_path: Path) -> None:
            nonlocal best
            if not package_path.is_file():
                return
            payload = self._read_package_json(package_path)
            if payload is None:
                return
            package_root = package_path.parent
            if self._is_excluded_package(package_root, payload):
                return
            scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
            score = self._script_score(scripts)
            if score <= 0:
                return
            depth = len(package_path.relative_to(root).parts)
            rank_key = (score, -depth)
            if best is None or rank_key > best[0]:
                best = (rank_key, package_path, payload)

        for relative in _PACKAGE_JSON_CANDIDATES:
            consider((root / relative / "package.json").resolve())

        for package_path in root.rglob("package.json"):
            if any(part in skip_dirs for part in package_path.parts):
                continue
            if len(package_path.relative_to(root).parts) > 5:
                continue
            consider(package_path)

        if best:
            _, package_path, payload = best
            return package_path.parent, payload
        return None, None

    @staticmethod
    def _read_package_json(package_path: Path) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _detect_from_package_json(self, package_root: Path, package: Dict[str, Any]) -> Dict[str, Any]:
        scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
        script_name = next((name for name in _SCRIPT_PRIORITY if name in scripts), None)
        if not script_name:
            return {
                "ok": False,
                "error": "package.json has no dev/start/frontend preview script.",
                "working_directory": str(package_root),
            }

        pm = self._package_manager(package_root)
        preview_root = package_root
        preview_package = package
        preview_script = script_name

        deps = self._dependency_names(package)
        if script_name == "dev" and "concurrently" in deps:
            for sub in ("frontend", "web", "client"):
                sub_path = package_root / sub / "package.json"
                sub_pkg = self._read_package_json(sub_path)
                if not sub_pkg:
                    continue
                sub_scripts = sub_pkg.get("scripts") if isinstance(sub_pkg.get("scripts"), dict) else {}
                if "dev" not in sub_scripts:
                    continue
                sub_fw = self._infer_framework(sub_path.parent, sub_pkg)
                if sub_fw in {"next", "vite", "vue", "svelte", "create-react-app"}:
                    preview_root = sub_path.parent
                    preview_package = sub_pkg
                    preview_script = "dev"
                    if pm == "yarn":
                        preview_command = f"yarn --cwd {sub} dev"
                    else:
                        preview_command = f"{pm} run dev --prefix {sub}"
                    framework = sub_fw
                    allocated = self.allocate_preview_launch(
                        preview_command=preview_command,
                        package_root=preview_root,
                        framework=framework,
                        script_name=preview_script,
                    )
                    return {
                        "ok": True,
                        "framework": framework,
                        "preview_command": allocated["preview_command"],
                        "preview_url": allocated["preview_url"],
                        "allocated_port": allocated["allocated_port"],
                        "port_note": allocated["port_note"],
                        "working_directory": str(package_root),
                        "source": f"package.json scripts.dev (monorepo via {sub}/)",
                        "package_manager": pm,
                    }

        if pm == "yarn":
            preview_command = f"yarn {preview_script}"
        else:
            preview_command = f"{pm} run {preview_script}"

        framework = self._infer_framework(preview_root, preview_package)
        allocated = self.allocate_preview_launch(
            preview_command=preview_command,
            package_root=preview_root,
            framework=framework,
            script_name=preview_script,
        )

        return {
            "ok": True,
            "framework": framework,
            "preview_command": allocated["preview_command"],
            "preview_url": allocated["preview_url"],
            "allocated_port": allocated["allocated_port"],
            "port_note": allocated["port_note"],
            "working_directory": str(package_root),
            "source": f"package.json scripts.{preview_script}",
            "package_manager": pm,
        }

    def _package_manager(self, package_root: Path) -> str:
        if (package_root / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (package_root / "yarn.lock").exists():
            return "yarn"
        if (package_root / "bun.lockb").exists() or (package_root / "bun.lock").exists():
            return "bun"
        return "npm"

    def _infer_framework(self, package_root: Path, package: Dict[str, Any]) -> str:
        deps = self._dependency_names(package)
        if "next" in deps:
            return "next"
        for sub in ("frontend", "web", "client", "apps/web", "apps/frontend"):
            sub_pkg_path = package_root / sub / "package.json"
            sub_pkg = self._read_package_json(sub_pkg_path)
            if sub_pkg and "next" in self._dependency_names(sub_pkg):
                return "next"
        if "vite" in deps or (package_root / "vite.config.ts").exists() or (package_root / "vite.config.js").exists():
            return "vite"
        if "react-scripts" in deps:
            return "create-react-app"
        if "@angular/core" in deps:
            return "angular"
        if "astro" in deps:
            return "astro"
        if "nuxt" in deps or "nuxt3" in deps:
            return "nuxt"
        if "vue" in deps:
            return "vue"
        if "svelte" in deps or "@sveltejs/kit" in deps:
            return "svelte"
        if "remix" in deps or "@remix-run/react" in deps:
            return "remix"
        if "express" in deps:
            return "node"
        return "node"

    @staticmethod
    def _dependency_names(package: Dict[str, Any]) -> set[str]:
        names: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            block = package.get(key)
            if isinstance(block, dict):
                names.update(str(name).lower() for name in block.keys())
        return names

    def _read_vite_port(self, package_root: Path) -> Optional[int]:
        for name in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
            config_path = package_root / name
            if not config_path.is_file():
                continue
            try:
                text = config_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            match = re.search(r"port\s*:\s*(\d+)", text)
            if match:
                return int(match.group(1))
        return None

    def _read_script_port(self, package_root: Path) -> Optional[int]:
        package = self._read_package_json(package_root / "package.json")
        if not package:
            return None
        scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
        for script_name in _SCRIPT_PRIORITY:
            script = str(scripts.get(script_name) or "")
            if not script:
                continue
            for pattern in (
                r"(?:--port|-p)\s+(\d+)",
                r"PORT=(\d+)",
                r":(\d{4,5})(?:/|$)",
            ):
                match = re.search(pattern, script)
                if match:
                    return int(match.group(1))
        return None

    def _read_configured_port(self, package_root: Path) -> Optional[int]:
        for reader in (self._read_vite_port, self._read_script_port):
            port = reader(package_root)
            if port is not None:
                return port
        return None

    @staticmethod
    def _port_is_free(port: int) -> bool:
        if port in _RESERVED_PREVIEW_PORTS:
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
            handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                handle.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def find_available_port(self, preferred: Optional[int] = None) -> int:
        if preferred is not None and preferred not in _RESERVED_PREVIEW_PORTS:
            try:
                return self.find_next_free_port(preferred)
            except RuntimeError:
                pass
        for port in _PREFERRED_PREVIEW_PORT_RANGE:
            if port in _RESERVED_PREVIEW_PORTS:
                continue
            if self._port_is_free(port):
                return port
        for fallback in (3000, 3001, 4321, 4200, 8080):
            if fallback in _RESERVED_PREVIEW_PORTS:
                continue
            if self._port_is_free(fallback):
                return fallback
        raise RuntimeError("No free TCP port found for project preview.")

    def find_next_free_port(self, starting_at: int, *, max_scan: int = 120) -> int:
        port = max(1, int(starting_at))
        for _ in range(max_scan):
            if port in _RESERVED_PREVIEW_PORTS:
                port += 1
                continue
            if self._port_is_free(port):
                return port
            port += 1
        raise RuntimeError(f"No free TCP port found near {starting_at} for project preview.")

    def allocate_preview_launch(
        self,
        *,
        preview_command: str,
        package_root: Path,
        framework: str,
        script_name: str,
        preferred_port: Optional[int] = None,
    ) -> Dict[str, Any]:
        configured_port = self._read_configured_port(package_root) or preferred_port
        start_port = configured_port
        if start_port is None:
            start_port = next(iter(_PREFERRED_PREVIEW_PORT_RANGE))
        if start_port in _RESERVED_PREVIEW_PORTS:
            start_port = next(
                port for port in _PREFERRED_PREVIEW_PORT_RANGE if port not in _RESERVED_PREVIEW_PORTS
            )
        port = self.find_next_free_port(start_port)
        command = self._with_port_override(preview_command, package_root, port, framework)
        configured_note = (
            f" (configured {configured_port}, port was in use)"
            if configured_port is not None and configured_port != port
            else (f" (configured {configured_port})" if configured_port is not None else "")
        )
        reserved_note = (
            f"Port {port} allocated for your app{configured_note}. "
            f"5173 is reserved for the Midnight Agent Space dashboard."
        )
        return {
            "preview_command": command,
            "preview_url": f"http://127.0.0.1:{port}",
            "allocated_port": port,
            "configured_port": configured_port,
            "port_note": reserved_note,
        }

    @staticmethod
    def preview_session_from_preferences(runtime_preferences: Dict[str, Any]) -> Dict[str, Any]:
        session = runtime_preferences.get("preview_session")
        return session if isinstance(session, dict) else {}

    @classmethod
    def build_preview_session(
        cls,
        *,
        preview_url: str,
        preview_command: str,
        working_directory: str,
        repo_path: str,
        pid: Optional[int] = None,
    ) -> Dict[str, Any]:
        session = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "preview_url": preview_url,
            "preview_command": preview_command,
            "working_directory": working_directory,
            "repo_path": repo_path,
            "phase": "launched",
        }
        if pid is not None:
            session["pid"] = pid
        return session

    def spawn_preview_process(self, *, preview_command: str, working_directory: Path) -> Dict[str, Any]:
        """Start dev server detached from the API process (Windows-friendly)."""
        cwd = working_directory.expanduser().resolve()
        if not cwd.exists():
            return {"ok": False, "error": f"Working directory does not exist: {cwd}"}

        log_dir = cwd / ".midnight" / "preview"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / "stdout.log"
        stderr_path = log_dir / "stderr.log"
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")

        popen_kwargs: Dict[str, Any] = {
            "shell": True,
            "cwd": str(cwd),
            "stdout": stdout_handle,
            "stderr": stderr_handle,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            popen_kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(preview_command, **popen_kwargs)
        except Exception as exc:  # noqa: BLE001
            stdout_handle.close()
            stderr_handle.close()
            return {"ok": False, "error": f"Failed to start preview process: {exc}"}
        stdout_handle.close()
        stderr_handle.close()
        return {
            "ok": True,
            "pid": process.pid,
            "command": preview_command,
            "cwd": str(cwd),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }

    @staticmethod
    def _parse_port(preview_url: str) -> Optional[int]:
        match = re.search(r":(\d+)(?:/|$)", preview_url)
        if not match:
            return None
        port = int(match.group(1))
        return port

    def _with_port_override(
        self,
        preview_command: str,
        package_root: Path,
        port: int,
        framework: str,
    ) -> str:
        if re.search(r"(?:--port|-p)\s+\d+", preview_command):
            return preview_command
        if framework == "next":
            return f"{preview_command} -- -p {port}"
        uses_vite = (
            framework in {"vite", "vue", "svelte"}
            or (package_root / "vite.config.ts").exists()
            or (package_root / "vite.config.js").exists()
            or (package_root / "vite.config.mjs").exists()
        )
        if uses_vite:
            return f"{preview_command} -- --host 127.0.0.1 --port {port}"
        if os.name == "nt":
            return f"set PORT={port}&& set HOST=127.0.0.1&& {preview_command}"
        return f"PORT={port} HOST=127.0.0.1 {preview_command}"

    async def probe_preview_url(self, preview_url: str) -> Dict[str, Any]:
        url = str(preview_url or "").strip()
        if not url:
            return {"reachable": False, "error": "No preview URL configured."}
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                response = await client.get(url)
                return {
                    "reachable": response.status_code < 500,
                    "status_code": response.status_code,
                    "final_url": str(response.url),
                }
        except httpx.TimeoutException:
            return {"reachable": False, "error": "Timed out waiting for dev server."}
        except httpx.RequestError as exc:
            return {"reachable": False, "error": str(exc)}

    async def preview_status(
        self,
        runtime_preferences: Dict[str, Any],
    ) -> Dict[str, Any]:
        prefs = runtime_preferences or {}
        session = self.preview_session_from_preferences(prefs)
        preview_url = str(session.get("preview_url") or prefs.get("preview_url") or "").strip()
        preview_command = str(session.get("preview_command") or prefs.get("preview_command") or "").strip()
        if not preview_url:
            return {
                "phase": "not_started",
                "reachable": False,
                "preview_url": None,
                "preview_command": preview_command or None,
                "message": "Preview has not been launched yet.",
            }
        if not session:
            probe = await self.probe_preview_url(preview_url)
            if probe.get("reachable"):
                return {
                    "phase": "ready",
                    "reachable": True,
                    "preview_url": preview_url,
                    "preview_command": preview_command or None,
                    "status_code": probe.get("status_code"),
                    "final_url": probe.get("final_url") or preview_url,
                    "message": "Dev server is responding.",
                }
            return {
                "phase": "not_started",
                "reachable": False,
                "preview_url": preview_url,
                "preview_command": preview_command or None,
                "message": "Preview URL is configured but the dev server is not running.",
            }

        probe = await self.probe_preview_url(preview_url)
        reachable = bool(probe.get("reachable"))
        phase = "ready" if reachable else str(session.get("phase") or "launched")
        if reachable:
            phase = "ready"
        elif phase not in {"launched", "ready"}:
            phase = "launched"
        return {
            "phase": phase,
            "reachable": reachable,
            "preview_url": preview_url,
            "preview_command": preview_command or session.get("preview_command"),
            "working_directory": session.get("working_directory"),
            "repo_path": session.get("repo_path"),
            "started_at": session.get("started_at"),
            "status_code": probe.get("status_code"),
            "final_url": probe.get("final_url") or preview_url,
            "error": probe.get("error"),
            "message": "Dev server is responding." if reachable else "Dev server is starting or not reachable yet.",
        }


preview_detection_service = PreviewDetectionService()
