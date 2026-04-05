"""
Dry run: prompt a task executor agent (OpenAI Agents SDK when available, else chat completions).

When openai-agents is installed, adheres to https://developers.openai.com/codex/guides/agents-sdk:
- load_dotenv(override=True), set_default_openai_api("chat_completions")
- Agent with instructions "You are a task executor agent"
- Runner.run(agent, input) and result.final_output

Otherwise uses OpenAI-compatible POST /chat/completions with the same system/user messages.

Uses OPENAI_API_KEY (or MIDNIGHT_AGENT_SPACE_AGENTS_API_KEY) from environment (e.g. temporal/.env).
Run from repo root: python -m temporal.dry_run_task_executor_agent
Or from temporal/: python dry_run_task_executor_agent.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on path and load .env from temporal/
if "__file__" in dir():
    _temporal_dir = Path(__file__).resolve().parent
    if str(_temporal_dir.parent) not in sys.path:
        sys.path.insert(0, str(_temporal_dir.parent))
    _env = _temporal_dir / ".env"
    if _env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_env, override=True)
        except Exception:
            pass


def _is_rate_limit_error(e: BaseException) -> bool:
    """True if the exception is due to 429 / rate limiting."""
    msg = (getattr(e, "message", "") or str(e)).lower()
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return True
    return type(e).__name__ == "RateLimitError"


async def _dry_run_sdk(api_key: str, api_url: str, model: str) -> None:
    """Run using OpenAI Agents SDK (doc-adherent)."""
    import logging
    # Suppress SDK/client "Error getting response; filtered.input=..." so 429 retries stay readable
    for _name in ("agents", "openai.agents", "openai"):
        _log = logging.getLogger(_name)
        _log.setLevel(logging.WARNING)

    from agents import Agent, Runner, RunConfig, set_default_openai_key, set_default_openai_api, set_default_openai_client
    from openai import AsyncOpenAI

    default_openai_url = "https://api.openai.com/v1"
    set_default_openai_key(api_key)
    set_default_openai_api("chat_completions")
    if api_url != default_openai_url:
        client = AsyncOpenAI(api_key=api_key, base_url=api_url)
        set_default_openai_client(client, use_for_tracing=False)

    instructions = "You are a task executor agent."
    user_input = "Reply with one short sentence confirming you are the task executor agent."

    agent = Agent(name="Task Executor", instructions=instructions)
    run_config = RunConfig(model=model)

    print(f"Dry run (OpenAI Agents SDK): model={model}, base_url={api_url}")
    print(f"  instructions: {instructions!r}")
    print(f"  user input:   {user_input!r}")
    print()

    result = await Runner.run(agent, user_input, run_config=run_config)
    out = getattr(result, "final_output", None) or ""
    print("Agent reply:")
    print(out if out else "(no final_output)")
    print("\nDry run completed successfully.")


async def _dry_run_chat_completions(api_key: str, api_url: str, model: str) -> None:
    """Fallback: raw chat completions (same system/user content as SDK path)."""
    import httpx

    system_content = "You are a task executor agent."
    user_content = "Reply with one short sentence confirming you are the task executor agent."

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "max_tokens": 150,
    }

    print(f"Dry run (chat completions): POST {api_url}/chat/completions (model={model})")
    print(f"  system: {system_content!r}")
    print(f"  user:   {user_content!r}")
    print()

    max_retries = 3
    retry_delay = 5.0
    r = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            r = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=60.0,
            )
            if r.status_code == 429:
                if attempt < max_retries - 1:
                    wait = retry_delay * (2**attempt)
                    print(f"429 Too Many Requests - retrying in {wait:.0f}s ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(wait)
                    continue
                print("429 Too Many Requests - rate limited. Try again later or use a different API key.")
                sys.exit(1)
            r.raise_for_status()
            break
    data = r.json()
    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content", "") if choices else ""
    print("Agent reply:")
    print(content or "(empty)")
    print("\nDry run completed successfully.")


async def _dry_run() -> None:
    from temporal.config import config

    api_key = (
        os.environ.get("MIDNIGHT_AGENT_SPACE_AGENTS_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or getattr(config.codex_api, "api_key", None)
        or getattr(config.openai, "api_key", None)
    )
    if not api_key:
        print(
            "No API key. Set MIDNIGHT_AGENT_SPACE_AGENTS_API_KEY or OPENAI_API_KEY "
            "in temporal/.env or export it."
        )
        sys.exit(1)

    api_url = (getattr(config.codex_api, "api_url", None) or "https://api.openai.com/v1").rstrip("/")
    model = getattr(config.codex_api, "model", "gpt-4.1-mini")

    use_sdk = False
    try:
        from agents import Agent, Runner  # noqa: F401
        use_sdk = True
    except ImportError:
        print("(OpenAI Agents SDK not installed; using chat completions. For doc-adherent agent creation: pip install openai-agents)\n")

    max_retries = 3
    retry_delay = 5.0
    last_error = None
    for attempt in range(max_retries):
        try:
            if use_sdk:
                await _dry_run_sdk(api_key, api_url, model)
            else:
                await _dry_run_chat_completions(api_key, api_url, model)
            return
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e) and attempt < max_retries - 1:
                wait = retry_delay * (2**attempt)
                print(f"429 Too Many Requests - retrying in {wait:.0f}s ({attempt + 1}/{max_retries})...")
                await asyncio.sleep(wait)
                continue
            if _is_rate_limit_error(e):
                print("429 Too Many Requests - rate limited. Try again later or use a different API key.")
                sys.exit(1)
            raise
    if last_error is not None:
        raise last_error


if __name__ == "__main__":
    asyncio.run(_dry_run())
