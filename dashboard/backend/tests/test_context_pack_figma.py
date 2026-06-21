"""Figma context pinning and excerpt extraction."""
from dashboard.backend.services.context_pack_service import ContextPackService


def test_figma_spec_excerpt_uses_document_type() -> None:
    service = ContextPackService()
    document = {
        "document_type": "figma_import",
        "content_kind": "text",
        "_structured": {
            "agent_context": {
                "text_preview": "Frame layout spec",
                "compact_spec": {"root_name": "Hero"},
            }
        },
    }
    excerpt = service._figma_spec_excerpt(document)
    assert excerpt == "Frame layout spec"


def test_compact_for_prompt_pins_figma_imports() -> None:
    service = ContextPackService()
    context_pack = {
        "project": {"project_id": 5, "project_name": "Test"},
        "project_metadata": {"runtime_preferences": {}, "metadata": {}},
        "rag_ready_context": {
            "documents": [
                {
                    "document_id": 1,
                    "name": "codebase.py",
                    "content_kind": "text",
                    "file_extension": ".py",
                    "text_preview": "def main(): pass",
                },
                {
                    "document_id": 2,
                    "name": "Figma: Home",
                    "content_kind": "figma_import",
                    "document_type": "figma_import",
                    "figma_spec_excerpt": "Home frame layout",
                    "figma_image_document_ids": [3],
                },
                {
                    "document_id": 3,
                    "name": "export",
                    "content_kind": "figma_export_image",
                    "document_type": "figma_export_image",
                },
            ],
            "retrieval_guidance": [],
        },
    }
    compact = service.compact_for_prompt(
        context_pack,
        task={"task_name": "Execute repo changes", "task_type": "implementation"},
        max_documents=1,
    )
    docs = compact["context_documents"]
    kinds = [str(doc.get("content_kind")).lower() for doc in docs]
    assert "figma_import" in kinds
    assert compact.get("design_context_required") is True
    figma_doc = next(doc for doc in docs if doc.get("content_kind") == "figma_import")
    assert figma_doc.get("pinned") is True
    assert "Home frame layout" in str(figma_doc.get("text_preview"))


def test_section_scoped_excerpt_for_implementation_task() -> None:
    service = ContextPackService()
    document = {
        "document_type": "figma_import",
        "_structured": {
            "agent_context": {
                "sections": [
                    {
                        "slug": "hero",
                        "name": "Hero",
                        "manifest_text": "Implement hero",
                        "node_count": 5,
                    }
                ],
            }
        },
    }
    task = {
        "task_name": "Implement section: hero",
        "task_type": "implementation",
        "task_data": {"design_section_slug": "hero"},
    }
    excerpt = service._figma_spec_excerpt(document, task=task)
    assert "hero" in excerpt
    assert len(excerpt) > 50


def test_relevance_boosts_figma_on_implementation_tasks() -> None:
    service = ContextPackService()
    figma_score = service._document_relevance_score(
        {"content_kind": "figma_import", "name": "Figma: Home"},
        "execute repo changes implementation",
    )
    text_score = service._document_relevance_score(
        {"content_kind": "text", "name": "notes.txt", "file_extension": ".txt"},
        "execute repo changes implementation",
    )
    assert figma_score > text_score
