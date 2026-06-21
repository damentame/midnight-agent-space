from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Windows cmd.exe has a ~8191 char command-line limit; keep argv prompts below this.
_WINDOWS_ARGV_PROMPT_MAX = 7000


@dataclass
class CursorAgentCapabilities:
    supports_print: bool = True
    supports_stream_json: bool = False
    supports_workspace: bool = False
    supports_model: bool = False
    supports_trust: bool = False


@dataclass
class CursorAgentRunPlan:
    prompt: str
    model: str
    worktree_path: Optional[str] = None
    output_json: bool = True
    extra_args: Optional[List[str]] = None


class CursorAgentRunner:
    def __init__(self) -> None:
        self._capability_cache: Dict[str, CursorAgentCapabilities] = {}

    @staticmethod
    def _resolve_argv(argv: List[str]) -> List[str]:
        if not argv:
            return argv
        resolved = list(argv)
        resolved_binary = shutil.which(resolved[0]) if resolved[0] else None
        if resolved_binary:
            resolved[0] = resolved_binary
        if os.name == "nt" and resolved and resolved[0].lower().endswith((".cmd", ".bat")):
            return ["cmd.exe", "/c", *resolved]
        return resolved

    async def _read_help(self, argv: List[str], timeout_seconds: int = 5) -> str:
        launch_argv = self._resolve_argv(argv)

        def run_help() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                launch_argv,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )

        try:
            completed = await asyncio.to_thread(run_help)
        except Exception:
            return ""
        return f"{completed.stdout or ''}\n{completed.stderr or ''}"

    async def detect_capabilities(self, cli_binary: str) -> CursorAgentCapabilities:
        resolved = shutil.which(cli_binary) or cli_binary
        if resolved in self._capability_cache:
            return self._capability_cache[resolved]

        root_help = (await self._read_help([resolved, "--help"])).lower()
        help_unavailable = len(root_help.strip()) < 20
        capabilities = CursorAgentCapabilities(
            supports_print=help_unavailable or "--print" in root_help or " -p" in root_help,
            supports_stream_json=help_unavailable or "stream-json" in root_help,
            supports_workspace="--workspace" in root_help,
            supports_model=help_unavailable or "--model" in root_help,
            supports_trust=help_unavailable or "--trust" in root_help or "--yolo" in root_help,
        )
        self._capability_cache[resolved] = capabilities
        return capabilities

    def build_command(
        self,
        cli_binary: str,
        plan: CursorAgentRunPlan,
        capabilities: CursorAgentCapabilities,
        *,
        include_prompt: bool = True,
    ) -> List[str]:
        cmd: List[str] = [cli_binary]
        # Headless dashboard runs must never block on workspace trust or interactive print mode.
        cmd.append("-p")
        if plan.output_json and capabilities.supports_stream_json:
            cmd.extend(["--output-format", "stream-json"])
        elif plan.output_json:
            cmd.extend(["--output-format", "json"])
        cmd.append("--trust")
        if plan.model and capabilities.supports_model:
            cmd.extend(["--model", plan.model])
        if plan.worktree_path and capabilities.supports_workspace:
            cmd.extend(["--workspace", plan.worktree_path])
        if plan.extra_args:
            cmd.extend(plan.extra_args)
        if include_prompt and plan.prompt:
            cmd.append(plan.prompt)
        return cmd

    @staticmethod
    def _prompt_file_path(worktree_path: Optional[str]) -> Optional[Path]:
        if not worktree_path:
            return None
        target = Path(worktree_path) / ".midnight" / "agent-prompt.md"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            return target
        except OSError:
            return None

    def _resolve_prompt_delivery(
        self,
        plan: CursorAgentRunPlan,
        *,
        include_prompt: bool,
    ) -> tuple[str, Optional[Path], str]:
        """Return (effective_prompt, prompt_file, delivery_mode)."""
        prompt = plan.prompt or ""
        if not include_prompt:
            return prompt, None, "omitted"

        if os.name == "nt" and len(prompt) > _WINDOWS_ARGV_PROMPT_MAX:
            prompt_file = self._prompt_file_path(plan.worktree_path)
            if prompt_file is not None:
                try:
                    prompt_file.write_text(prompt, encoding="utf-8")
                    relative = prompt_file.name
                    try:
                        relative = str(prompt_file.relative_to(Path(plan.worktree_path or ".")))
                    except ValueError:
                        pass
                    return (
                        f"Read and execute the task instructions in {relative}. "
                        "Open that file in the workspace and follow it completely.",
                        prompt_file,
                        "prompt_file",
                    )
                except OSError:
                    pass
        return prompt, None, "argv"

    def parse_event_line(self, line: str, ordinal: int) -> Optional[Dict[str, Any]]:
        raw = line.strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "event_type": "stdout",
                "event_order": ordinal,
                "message": raw,
                "raw": raw,
            }
        event_type = payload.get("type") or payload.get("event") or payload.get("kind") or "unknown"
        message = payload.get("message") or payload.get("text") or payload.get("content")
        return {
            "event_type": str(event_type),
            "event_order": ordinal,
            "payload": payload,
            "message": message if isinstance(message, str) else None,
        }

    @staticmethod
    def _needs_sync_subprocess() -> bool:
        if os.name != "nt":
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return type(loop).__name__ == "SelectorEventLoop"

    def _execute_sync_subprocess(
        self,
        *,
        launch_command: List[str],
        command: List[str],
        plan: CursorAgentRunPlan,
        worktree_path: Optional[str],
        timeout_seconds: int,
        capabilities: CursorAgentCapabilities,
        emit_sync: Callable[[Dict[str, Any]], None],
        started: float,
        prompt_delivery: str = "argv",
        prompt_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        events_seen = 0
        stdout_tail: List[str] = []
        stderr_tail: List[str] = []
        ordinal = 0
        ordinal_lock = threading.Lock()

        def keep_tail(bucket: List[str], value: str, max_lines: int = 200) -> None:
            bucket.append(value)
            if len(bucket) > max_lines:
                del bucket[:-max_lines]

        def emit(event: Dict[str, Any]) -> None:
            nonlocal events_seen
            events_seen += 1
            emit_sync(event)

        def pump_stream(stream: Any, stream_name: str) -> None:
            nonlocal ordinal
            if stream is None:
                return
            for raw in stream:
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                with ordinal_lock:
                    ordinal += 1
                    current_ordinal = ordinal
                if stream_name == "stdout":
                    keep_tail(stdout_tail, text)
                    parsed = self.parse_event_line(text, current_ordinal)
                    event = parsed or {
                        "event_type": "stdout",
                        "event_order": current_ordinal,
                        "message": text,
                        "raw": text,
                    }
                else:
                    keep_tail(stderr_tail, text)
                    event = {
                        "event_type": "stderr",
                        "event_order": current_ordinal,
                        "message": text,
                        "raw": text,
                    }
                emit(event)

        emit(
            {
                "event_type": "process_start",
                "event_order": 0,
                "payload": {
                    "command": command,
                    "prompt_delivery": prompt_delivery,
                    "prompt_file": str(prompt_file) if prompt_file else None,
                    "cwd": worktree_path,
                },
            }
        )

        try:
            process = subprocess.Popen(
                launch_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=worktree_path or None,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": f"cursor-agent binary not found: {command[0]}",
                "command": command,
                "capabilities": asdict(capabilities),
                "event_count": 0,
                "stdout_tail": [],
                "stderr_tail": [],
            }
        except OSError as exc:
            return {
                "ok": False,
                "error": f"failed to launch cursor-agent: {type(exc).__name__}: {exc}",
                "command": command,
                "capabilities": asdict(capabilities),
                "event_count": 0,
                "stdout_tail": [],
                "stderr_tail": [],
            }

        timed_out = False
        exit_code = -1
        wait_error: Optional[str] = None
        try:
            stdout_thread = threading.Thread(target=pump_stream, args=(process.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=pump_stream, args=(process.stderr, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            exit_code = process.wait(timeout=timeout_seconds)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = process.wait(timeout=10)
            emit(
                {
                    "event_type": "timeout",
                    "event_order": None,
                    "payload": {"timeout_seconds": timeout_seconds},
                }
            )
        except Exception as exc:  # noqa: BLE001
            wait_error = f"{type(exc).__name__}: {exc}"
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass
            try:
                exit_code = process.wait(timeout=5)
            except Exception:  # noqa: BLE001
                exit_code = -1

        emit(
            {
                "event_type": "process_exit",
                "event_order": None,
                "payload": {
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "error": wait_error,
                },
            }
        )

        error_message: Optional[str] = None
        for raw_line in [*stdout_tail, *stderr_tail]:
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") in {"error", "turn.failed"}:
                error_payload = payload.get("error") or payload
                if isinstance(error_payload, dict):
                    error_message = str(error_payload.get("message") or error_message or "")
                else:
                    error_message = str(error_payload)
        if not error_message and stderr_tail:
            error_message = stderr_tail[-1]

        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": (exit_code == 0) and not timed_out,
            "error": error_message if (exit_code != 0 or timed_out) else None,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "elapsed_ms": elapsed_ms,
            "command": command,
            "capabilities": asdict(capabilities),
            "event_count": events_seen,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
        }

    _SYNC_DONE = object()

    async def _execute_sync_subprocess_async(
        self,
        *,
        launch_command: List[str],
        command: List[str],
        plan: CursorAgentRunPlan,
        worktree_path: Optional[str],
        timeout_seconds: int,
        capabilities: CursorAgentCapabilities,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        started: float,
        prompt_delivery: str = "argv",
        prompt_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit_sync(event: Dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        async def drain_events() -> None:
            while True:
                item = await queue.get()
                if item is self._SYNC_DONE:
                    break
                if event_callback:
                    await event_callback(item)

        drain_task = asyncio.create_task(drain_events())
        try:
            return await asyncio.to_thread(
                self._execute_sync_subprocess,
                launch_command=launch_command,
                command=command,
                plan=plan,
                worktree_path=worktree_path,
                timeout_seconds=timeout_seconds,
                capabilities=capabilities,
                emit_sync=emit_sync,
                started=started,
                prompt_delivery=prompt_delivery,
                prompt_file=prompt_file,
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, self._SYNC_DONE)
            await drain_task

    async def execute_streaming(
        self,
        *,
        cli_binary: str,
        plan: CursorAgentRunPlan,
        timeout_seconds: int,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        capabilities = await self.detect_capabilities(cli_binary)
        effective_prompt, prompt_file, prompt_delivery = self._resolve_prompt_delivery(
            plan,
            include_prompt=True,
        )
        command_plan = CursorAgentRunPlan(
            prompt=effective_prompt,
            model=plan.model,
            worktree_path=plan.worktree_path,
            output_json=plan.output_json,
            extra_args=plan.extra_args,
        )
        command = self.build_command(cli_binary, command_plan, capabilities, include_prompt=True)
        worktree_path = plan.worktree_path
        started = time.monotonic()
        launch_command = self._resolve_argv(command)
        if self._needs_sync_subprocess():
            return await self._execute_sync_subprocess_async(
                launch_command=launch_command,
                command=command,
                plan=command_plan,
                worktree_path=worktree_path,
                timeout_seconds=timeout_seconds,
                capabilities=capabilities,
                event_callback=event_callback,
                started=started,
                prompt_delivery=prompt_delivery,
                prompt_file=prompt_file,
            )
        return await self._execute_sync_subprocess_async(
            launch_command=launch_command,
            command=command,
            plan=command_plan,
            worktree_path=worktree_path,
            timeout_seconds=timeout_seconds,
            capabilities=capabilities,
            event_callback=event_callback,
            started=started,
            prompt_delivery=prompt_delivery,
            prompt_file=prompt_file,
        )


cursor_agent_runner = CursorAgentRunner()
