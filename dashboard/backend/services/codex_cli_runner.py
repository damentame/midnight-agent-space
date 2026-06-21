from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class CodexCliCapabilities:
    supports_exec: bool
    supports_json: bool = True
    supports_ask_for_approval: bool = False
    supports_sandbox: bool = False
    supports_cd: bool = False
    cd_flag: str = "--cd"
    supports_output_schema: bool = False
    supports_output_path: bool = False


@dataclass
class CodexCliRunPlan:
    prompt: str
    model: str
    worktree_path: Optional[str] = None
    output_json: bool = True
    max_output_tokens: Optional[int] = None
    output_schema_path: Optional[str] = None
    output_path: Optional[str] = None
    extra_args: Optional[List[str]] = None
    approval_mode: Optional[str] = None
    sandbox_mode: Optional[str] = None


class CodexCliRunner:
    def __init__(self) -> None:
        self._capability_cache: Dict[str, CodexCliCapabilities] = {}

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

    async def detect_capabilities(self, cli_binary: str) -> CodexCliCapabilities:
        resolved = shutil.which(cli_binary) or cli_binary
        if resolved in self._capability_cache:
            return self._capability_cache[resolved]

        root_help = (await self._read_help([resolved, "--help"])).lower()
        exec_help = (await self._read_help([resolved, "exec", "--help"])).lower()
        run_help = (await self._read_help([resolved, "run", "--help"])).lower()

        supports_exec = True
        active_help = exec_help or root_help or run_help

        supports_cd = "--cd" in active_help or "--cwd" in active_help
        if supports_exec and not active_help.strip():
            capabilities = CodexCliCapabilities(
                supports_exec=True,
                supports_json=True,
                supports_ask_for_approval=False,
                supports_sandbox=True,
                supports_cd=True,
                cd_flag="--cd",
                supports_output_schema=True,
                supports_output_path=True,
            )
            self._capability_cache[resolved] = capabilities
            return capabilities
        capabilities = CodexCliCapabilities(
            supports_exec=supports_exec,
            supports_json="--json" in active_help,
            supports_ask_for_approval="--ask-for-approval" in active_help,
            supports_sandbox="--sandbox" in active_help,
            supports_cd=supports_cd,
            cd_flag="--cd" if "--cd" in active_help else "--cwd",
            supports_output_schema="--output-schema" in active_help,
            supports_output_path="-o" in active_help or "--output" in active_help,
        )
        self._capability_cache[resolved] = capabilities
        return capabilities

    @staticmethod
    def _sanitize_approval_mode(mode: Optional[str]) -> str:
        value = (mode or "").strip().lower()
        if not value:
            return "never"
        dangerous_tokens = ("bypass", "danger", "off", "none", "disable")
        if any(token in value for token in dangerous_tokens):
            return "never"
        return value

    @staticmethod
    def _sanitize_sandbox_mode(mode: Optional[str]) -> str:
        value = (mode or "").strip().lower()
        if not value:
            return "workspace-write"
        dangerous_tokens = ("danger", "bypass", "off", "none", "disable")
        if any(token in value for token in dangerous_tokens):
            return "workspace-write"
        return value

    def build_command(
        self,
        cli_binary: str,
        plan: CodexCliRunPlan,
        capabilities: CodexCliCapabilities,
        *,
        include_prompt: bool = True,
    ) -> List[str]:
        if capabilities.supports_exec:
            cmd: List[str] = [cli_binary, "exec"]
            if plan.output_json and capabilities.supports_json:
                cmd.append("--json")
            if capabilities.supports_ask_for_approval:
                cmd.extend(["--ask-for-approval", self._sanitize_approval_mode(plan.approval_mode)])
            if capabilities.supports_sandbox:
                cmd.extend(["--sandbox", self._sanitize_sandbox_mode(plan.sandbox_mode)])
            if plan.worktree_path and capabilities.supports_cd:
                cmd.extend([capabilities.cd_flag, plan.worktree_path])
            if plan.model:
                cmd.extend(["--model", plan.model])
            if plan.max_output_tokens and plan.max_output_tokens > 0:
                cmd.extend(["--max-output-tokens", str(plan.max_output_tokens)])
            if plan.output_schema_path and capabilities.supports_output_schema:
                cmd.extend(["--output-schema", plan.output_schema_path])
            if plan.output_path and capabilities.supports_output_path:
                cmd.extend(["-o", plan.output_path])
            if plan.extra_args:
                cmd.extend(plan.extra_args)
            cmd.append(plan.prompt if include_prompt else "-")
            return cmd

        # Compatibility fallback for older Codex CLI.
        cmd = [cli_binary, "run"]
        if plan.output_json:
            cmd.append("--json")
        if plan.model:
            cmd.extend(["--model", plan.model])
        if plan.worktree_path:
            cmd.extend(["--cwd", plan.worktree_path])
        if plan.max_output_tokens and plan.max_output_tokens > 0:
            cmd.extend(["--max-output-tokens", str(plan.max_output_tokens)])
        if plan.extra_args:
            cmd.extend(plan.extra_args)
        cmd.extend(["--prompt", plan.prompt if include_prompt else "<prompt via stdin>"])
        return cmd

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
        return {
            "event_type": str(event_type),
            "event_order": ordinal,
            "payload": payload,
            "message": payload.get("message"),
        }

    def parse_event_stream(self, lines: List[str]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines, start=1):
            parsed = self.parse_event_line(line, idx)
            if parsed:
                events.append(parsed)
        return events

    async def execute_streaming(
        self,
        *,
        cli_binary: str,
        plan: CodexCliRunPlan,
        timeout_seconds: int,
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        capabilities = await self.detect_capabilities(cli_binary)
        command = self.build_command(cli_binary, plan, capabilities, include_prompt=False)

        started = time.monotonic()
        events_seen = 0
        stdout_tail: List[str] = []
        stderr_tail: List[str] = []
        ordinal = 0
        ordinal_lock = asyncio.Lock()

        def keep_tail(bucket: List[str], value: str, max_lines: int = 200) -> None:
            bucket.append(value)
            if len(bucket) > max_lines:
                del bucket[:-max_lines]

        async def emit(event: Dict[str, Any]) -> None:
            nonlocal events_seen
            events_seen += 1
            if event_callback:
                await event_callback(event)

        try:
            launch_command = self._resolve_argv(command)
            process = await asyncio.create_subprocess_exec(
                *launch_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": f"cli binary not found: {cli_binary}",
                "command": command,
                "capabilities": asdict(capabilities),
                "event_count": 0,
                "stdout_tail": [],
                "stderr_tail": [],
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"failed to launch Codex CLI: {type(exc).__name__}: {exc}",
                "command": command,
                "capabilities": asdict(capabilities),
                "event_count": 0,
                "stdout_tail": [],
                "stderr_tail": [],
            }

        async def pump_stream(stream: Any, stream_name: str) -> None:
            nonlocal ordinal
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                async with ordinal_lock:
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
                await emit(event)

        await emit(
            {
                "event_type": "process_start",
                "event_order": 0,
                "payload": {"command": command, "prompt_delivery": "stdin"},
            }
        )

        if process.stdin:
            try:
                process.stdin.write(plan.prompt.encode("utf-8"))
                await process.stdin.drain()
            finally:
                process.stdin.close()

        stdout_task = asyncio.create_task(pump_stream(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(pump_stream(process.stderr, "stderr"))

        timed_out = False
        try:
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            exit_code = await process.wait()
            await emit(
                {
                    "event_type": "timeout",
                    "event_order": None,
                    "payload": {"timeout_seconds": timeout_seconds},
                }
            )

        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        await emit(
            {
                "event_type": "process_exit",
                "event_order": None,
                "payload": {"exit_code": exit_code, "timed_out": timed_out},
            }
        )

        error_message: Optional[str] = None
        for raw_line in [*stdout_tail, *stderr_tail]:
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "error":
                error_message = str(payload.get("message") or "")
            elif payload.get("type") == "turn.failed":
                error_payload = payload.get("error") or {}
                if isinstance(error_payload, dict):
                    error_message = str(error_payload.get("message") or error_message or "")
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


codex_cli_runner = CodexCliRunner()
