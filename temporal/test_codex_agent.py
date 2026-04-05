import asyncio
from typing import Any, Dict


async def _run_test() -> None:
    """
    Minimal, direct test of the Codex/OpenAI-backed task executor.

    This bypasses Temporal and calls the internal Codex helper used by
    `execute_task_with_agent_activity` so we can quickly verify that
    credentials, URL, and model are working.
    """
    from temporal.activities.task_execution_activities import _execute_task_with_codex_agent

    # Trivial "task" payload; only description is actually used to build the prompt.
    task: Dict[str, Any] = {
        "task_id": 0,
        "task_name": "Test Codex connectivity",
        "description": "Respond with a short confirmation that Codex connectivity is working.",
    }
    rag_context: Dict[str, Any] = {}

    result = await _execute_task_with_codex_agent(
        task=task,
        project_id=1,
        agent_id=0,
        agent_instance_id=0,
        rag_context=rag_context,
        workspace_root=None,
    )

    print("Codex test result:")
    print(result)


if __name__ == "__main__":
    asyncio.run(_run_test())

