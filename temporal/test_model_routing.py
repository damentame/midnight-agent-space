"""Unit tests for temporal.utils.model_routing."""
import sys
from pathlib import Path

parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))


def test_infer_execution_complexity() -> None:
    from temporal.utils.model_routing import infer_execution_complexity

    assert infer_execution_complexity({"task_data": {"execution_complexity": "complex"}}, "fast") == "complex"
    assert infer_execution_complexity({"task_type": "research"}, "fast") == "complex"
    assert infer_execution_complexity({"task_type": "implementation"}, "fast") == "fast"


def test_effective_batch_chain_execute_mode() -> None:
    from temporal.utils.model_routing import effective_batch_chain_execute_mode

    peek = [
        {"task_type": "implementation", "task_data": {"execution_complexity": "fast"}},
        {"task_type": "research"},
    ]
    assert effective_batch_chain_execute_mode(peek, "fast") == "complex"
    assert effective_batch_chain_execute_mode(peek[:1], "fast") == "fast"


def test_resolve_executor_model_uses_task_type() -> None:
    from temporal.utils.model_routing import resolve_executor_model

    m = resolve_executor_model("fast", "cursor", {"task_type": "research"})
    # Cursor may omit model (None) when tier env vars unset; Codex always returns str
    assert m is None or isinstance(m, str)

    m2 = resolve_executor_model("complex", "codex", {"task_type": "implementation"})
    assert isinstance(m2, str) and len(m2) > 0


def test_resolve_executor_model_claude_code() -> None:
    from temporal.utils.model_routing import resolve_executor_model

    m_fast = resolve_executor_model("fast", "claude-code", None)
    assert isinstance(m_fast, str) and len(m_fast) > 0

    m_complex = resolve_executor_model("complex", "claude-code", {"task_type": "research"})
    assert isinstance(m_complex, str) and len(m_complex) > 0

    m_task = resolve_executor_model("fast", "claude-code", {"task_type": "documentation"})
    assert isinstance(m_task, str) and len(m_task) > 0


def test_resolve_serialization_model() -> None:
    from temporal.utils.model_routing import resolve_serialization_model

    a = resolve_serialization_model("fast")
    b = resolve_serialization_model("complex")
    assert a is None or isinstance(a, str)
    assert b is None or isinstance(b, str)


if __name__ == "__main__":
    test_infer_execution_complexity()
    test_effective_batch_chain_execute_mode()
    test_resolve_executor_model_uses_task_type()
    test_resolve_executor_model_claude_code()
    test_resolve_serialization_model()
    print("model_routing tests passed")
