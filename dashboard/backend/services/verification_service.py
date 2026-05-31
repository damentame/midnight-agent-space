from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class VerificationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class CommandExecutionResult:
    ok: bool
    command: List[str]
    exit_code: int
    stdout: str
    stderr: str
    elapsed_ms: int
    timed_out: bool = False


class VerificationService:
    """Validation and preflight checks for quick-runs."""

    _DOCKER_EXECUTABLES = {
        "docker",
        "docker.exe",
        "docker-compose",
        "docker-compose.exe",
        "podman",
        "podman.exe",
        "nerdctl",
        "nerdctl.exe",
    }
    _DOCKER_RUNTIME_FLAGS = {"--runtime", "--container-runtime"}
    _DOCKER_MODE_FLAGS = {"--docker", "--use-docker"}
    _FLAGS_REQUIRING_VALUE = {
        "--ask-for-approval",
        "--cd",
        "--container-runtime",
        "--cwd",
        "--model",
        "--output",
        "--output-schema",
        "--project-id",
        "--prompt",
        "--provider",
        "--runtime",
        "--sandbox",
        "--max-output-tokens",
        "-o",
    }

    def verify_quick_run_inputs(
        self,
        *,
        project_id: int,
        user_prompt: str,
        runtime_provider: str,
        template_name: str,
    ) -> VerificationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if project_id <= 0:
            errors.append("project_id must be a positive integer")
        if not user_prompt.strip():
            errors.append("user_prompt is required")
        if len(user_prompt) > 20000:
            warnings.append("user_prompt is large; consider reducing context size")
        if runtime_provider not in {"codex-cli", "cursor", "codex", "claude-code"}:
            errors.append(f"unsupported runtime_provider '{runtime_provider}'")
        if not template_name.strip():
            errors.append("template_name is required")

        return VerificationResult(ok=not errors, errors=errors, warnings=warnings)

    def verify_command_preview(self, argv: List[str]) -> VerificationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if not argv:
            errors.append("command preview is empty")
            return VerificationResult(ok=False, errors=errors, warnings=warnings)

        executable = argv[0].rsplit("\\", maxsplit=1)[-1].rsplit("/", maxsplit=1)[-1].lower()
        if executable in self._DOCKER_EXECUTABLES:
            errors.append("docker-based execution is not allowed in this phase")

        # Only inspect executable + flags. Stop scanning when command transitions
        # into positional args (for example, the long prompt argument).
        seen_subcommand = False
        idx = 1
        while idx < len(argv):
            token = str(argv[idx] or "")
            token_lower = token.lower()

            if not token.startswith("-"):
                if not seen_subcommand:
                    seen_subcommand = True
                    idx += 1
                    continue
                break

            seen_subcommand = True
            flag_name, has_inline_value, inline_value = token_lower.partition("=")

            if flag_name in self._DOCKER_MODE_FLAGS:
                errors.append("docker-based execution is not allowed in this phase")

            if flag_name in self._DOCKER_RUNTIME_FLAGS:
                runtime_value = inline_value if has_inline_value else ""
                if not runtime_value and (idx + 1) < len(argv):
                    runtime_value = str(argv[idx + 1] or "").strip().lower()
                if runtime_value == "docker":
                    errors.append("docker-based execution is not allowed in this phase")

            if flag_name == "--dangerously-bypass-permissions":
                errors.append("permission bypass flag is not allowed in this phase")

            if (not has_inline_value) and (flag_name in self._FLAGS_REQUIRING_VALUE) and (idx + 1) < len(argv):
                idx += 1
            idx += 1

        return VerificationResult(ok=not errors, errors=errors, warnings=warnings)

    async def run_command(
        self,
        argv: List[str],
        *,
        cwd: Optional[str] = None,
        timeout_seconds: int = 30,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandExecutionResult:
        started = time.monotonic()
        if not argv:
            return CommandExecutionResult(
                ok=False,
                command=[],
                exit_code=127,
                stdout="",
                stderr="command not found: <empty>",
                elapsed_ms=0,
                timed_out=False,
            )

        resolved_argv = list(argv)
        resolved_binary = shutil.which(resolved_argv[0]) if resolved_argv[0] else None
        if resolved_binary:
            resolved_argv[0] = resolved_binary

        try:
            process = await asyncio.create_subprocess_exec(
                *resolved_argv,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return CommandExecutionResult(
                ok=False,
                command=argv,
                exit_code=127,
                stdout="",
                stderr=f"command not found: {argv[0] if argv else '<empty>'}",
                elapsed_ms=0,
                timed_out=False,
            )

        timed_out = False
        try:
            stdout_raw, stderr_raw = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
            exit_code = process.returncode or 0
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            stdout_raw, stderr_raw = await process.communicate()
            exit_code = process.returncode or 124

        elapsed_ms = int((time.monotonic() - started) * 1000)
        stdout = (stdout_raw or b"").decode("utf-8", errors="replace")
        stderr = (stderr_raw or b"").decode("utf-8", errors="replace")
        return CommandExecutionResult(
            ok=(exit_code == 0) and (not timed_out),
            command=argv,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            elapsed_ms=elapsed_ms,
            timed_out=timed_out,
        )


verification_service = VerificationService()
