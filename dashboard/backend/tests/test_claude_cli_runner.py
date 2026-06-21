"""Claude CLI command construction."""
from dashboard.backend.services.claude_cli_runner import (
    ClaudeCliCapabilities,
    ClaudeCliRunPlan,
    ClaudeCliRunner,
)


def test_prompt_immediately_follows_print_flag() -> None:
    runner = ClaudeCliRunner()
    plan = ClaudeCliRunPlan(prompt="Review the implementation", model="haiku")
    caps = ClaudeCliCapabilities(supports_stream_json=True)
    cmd = runner.build_command("claude", plan, caps, include_prompt=True)
    assert cmd[0] == "claude"
    assert cmd[1] == "-p"
    assert cmd[2] == "Review the implementation"
    assert "--output-format" in cmd
    assert cmd[-1] != "Review the implementation"  # prompt must not be trailing after flags


def test_no_stdin_placeholder() -> None:
    runner = ClaudeCliRunner()
    plan = ClaudeCliRunPlan(prompt="", model="haiku")
    caps = ClaudeCliCapabilities()
    cmd = runner.build_command("claude", plan, caps, include_prompt=False)
    assert cmd[0:2] == ["claude", "-p"]
    assert "-" not in cmd
