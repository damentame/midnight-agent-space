"""Cursor Agent runner prompt delivery and command construction."""
import os
from unittest.mock import patch

from dashboard.backend.services.cursor_agent_runner import (
    CursorAgentCapabilities,
    CursorAgentRunPlan,
    CursorAgentRunner,
    _WINDOWS_ARGV_PROMPT_MAX,
)


def test_short_prompt_delivered_via_argv() -> None:
    runner = CursorAgentRunner()
    plan = CursorAgentRunPlan(prompt="Build the login page", model="auto")
    caps = CursorAgentCapabilities(supports_print=True)
    prompt, prompt_file, mode = runner._resolve_prompt_delivery(plan, include_prompt=True)
    assert mode == "argv"
    assert prompt_file is None
    cmd = runner.build_command("cursor-agent", plan, caps, include_prompt=False)
    cmd_with_prompt = runner.build_command(
        "cursor-agent",
        CursorAgentRunPlan(prompt=prompt, model=plan.model),
        caps,
        include_prompt=True,
    )
    assert "-p" in cmd_with_prompt
    assert "--trust" in cmd_with_prompt
    assert cmd_with_prompt[-1] == "Build the login page"
    assert "-" not in cmd  # never stdin


def test_long_prompt_on_windows_uses_prompt_file(tmp_path) -> None:
    runner = CursorAgentRunner()
    worktree = str(tmp_path)
    long_prompt = "x" * (_WINDOWS_ARGV_PROMPT_MAX + 100)
    plan = CursorAgentRunPlan(prompt=long_prompt, model="auto", worktree_path=worktree)
    with patch.object(os, "name", "nt"):
        prompt, prompt_file, mode = runner._resolve_prompt_delivery(plan, include_prompt=True)
    assert mode == "prompt_file"
    assert prompt_file is not None
    assert prompt_file.exists()
    assert "agent-prompt.md" in str(prompt_file)
    assert "Read and execute" in prompt


def test_process_exit_emitted_on_wait_failure() -> None:
    runner = CursorAgentRunner()
    events: list = []

    class BrokenProcess:
        stdout = None
        stderr = None

        def wait(self, timeout=None):
            raise OSError("broken pipe")

        def kill(self):
            pass

    with patch("dashboard.backend.services.cursor_agent_runner.subprocess.Popen", return_value=BrokenProcess()):
        result = runner._execute_sync_subprocess(
            launch_command=["cursor-agent", "-p", "hi"],
            command=["cursor-agent", "-p", "hi"],
            plan=CursorAgentRunPlan(prompt="hi", model="auto"),
            worktree_path=None,
            timeout_seconds=5,
            capabilities=CursorAgentCapabilities(),
            emit_sync=events.append,
            started=0.0,
        )

    exit_events = [event for event in events if event.get("event_type") == "process_exit"]
    assert len(exit_events) == 1
    assert exit_events[0]["payload"]["error"]
    assert result["ok"] is False
