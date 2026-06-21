from __future__ import annotations

from typing import Any, Dict, List, Optional


class ReviewCheckService:
    """
    Deterministic post-run checks for demo visibility.
    """

    def build_review(
        self,
        *,
        run_status: str,
        execution_result: Dict[str, Any],
        diff_summary: Dict[str, Any],
        artifact_count: int,
        context_pack: Dict[str, Any] | None = None,
        design_fidelity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        context_pack = context_pack or {}
        rag_context = context_pack.get("rag_ready_context") or {}
        documents = rag_context.get("documents") or []
        design_assets = rag_context.get("design_assets") or []
        figma_imports = [
            doc for doc in documents if str(doc.get("content_kind") or "").lower() == "figma_import"
        ]
        figma_links = [
            doc
            for doc in documents
            if "figma.com" in str(doc.get("text_preview") or "").lower()
            or str(doc.get("content_kind") or "").lower() == "figma_design"
        ]

        checks.append(
            {
                "check": "run_status_terminal",
                "ok": run_status in {"COMPLETED", "FAILED", "CANCELLED", "PLANNED", "BLOCKED"},
                "value": run_status,
            }
        )
        checks.append(
            {
                "check": "process_exit_zero",
                "ok": execution_result.get("exit_code") in (None, 0),
                "value": execution_result.get("exit_code"),
            }
        )
        checks.append(
            {
                "check": "timeout_not_triggered",
                "ok": not bool(execution_result.get("timed_out")),
                "value": bool(execution_result.get("timed_out")),
            }
        )
        checks.append(
            {
                "check": "artifacts_captured",
                "ok": artifact_count > 0,
                "value": artifact_count,
            }
        )
        checks.append(
            {
                "check": "git_changes_recorded",
                "ok": int(diff_summary.get("inserted", 0)) >= 0,
                "value": int(diff_summary.get("inserted", 0)),
            }
        )
        checks.append(
            {
                "check": "context_documents_available",
                "ok": len(documents) > 0,
                "value": len(documents),
            }
        )
        checks.append(
            {
                "check": "design_references_identified",
                "ok": bool(design_assets or figma_links or figma_imports),
                "value": {
                    "design_assets": len(design_assets),
                    "figma_imports": len(figma_imports),
                    "figma_links": len(figma_links),
                },
            }
        )

        fidelity = design_fidelity or execution_result.get("design_fidelity") or {}
        if fidelity and not fidelity.get("skipped"):
            checks.append(
                {
                    "check": "stock_photos_absent",
                    "ok": bool((fidelity.get("stock_photos") or {}).get("ok", True)),
                    "value": fidelity.get("stock_photos"),
                }
            )
            checks.append(
                {
                    "check": "design_assets_used",
                    "ok": bool((fidelity.get("assets_used") or {}).get("ok", True)),
                    "value": fidelity.get("assets_used"),
                }
            )
            checks.append(
                {
                    "check": "sections_implemented",
                    "ok": bool((fidelity.get("section_landmarks") or {}).get("ok", True)),
                    "value": fidelity.get("section_landmarks"),
                }
            )
            visual = fidelity.get("visual_fidelity") or {}
            checks.append(
                {
                    "check": "visual_fidelity_scored",
                    "ok": True,
                    "advisory": True,
                    "value": visual.get("sections"),
                }
            )

        all_ok = all(bool(check.get("ok")) for check in checks if not check.get("advisory"))
        design_gaps: List[str] = []
        if figma_links and not design_assets and not figma_imports:
            design_gaps.append(
                "Only Figma prototype links were available in context; no local SVG/image/design asset was available for deterministic visual comparison."
            )
            all_ok = False
        if not design_assets and not figma_links and not figma_imports:
            design_gaps.append("No design reference was available in the context pack.")

        if fidelity and fidelity.get("blocking_failures"):
            design_gaps.extend(
                [f"Structural fidelity failed: {name}" for name in fidelity["blocking_failures"]]
            )
            all_ok = False

        structural_blocking = bool(
            fidelity
            and fidelity.get("hard_block_enabled")
            and not fidelity.get("structural_pass")
        )

        changed_files = diff_summary.get("changed_files") or diff_summary.get("status_lines") or []
        feature_review = {
            "scope": "feature",
            "recommendation": "approved" if all_ok and not design_gaps else "needs_changes",
            "summary": (
                "Feature run completed with inspectable context."
                if all_ok and not design_gaps
                else "Feature run needs review because design context is incomplete or checks failed."
            ),
            "context_used": [
                {
                    "document_id": doc.get("document_id"),
                    "name": doc.get("name"),
                    "content_kind": doc.get("content_kind"),
                    "text_preview": doc.get("text_preview"),
                }
                for doc in documents
            ],
            "design_references_used": [
                {
                    "document_id": doc.get("document_id"),
                    "name": doc.get("name"),
                    "content_kind": doc.get("content_kind"),
                    "text_preview": doc.get("text_preview"),
                }
                for doc in [*design_assets, *figma_links]
            ],
            "design_reference_gaps": design_gaps,
            "design_gaps_blocking": structural_blocking
            or bool(figma_links and not design_assets and not figma_imports),
            "design_fidelity": fidelity,
            "changed_files": changed_files,
            "artifact_count": artifact_count,
        }
        return {"ok": all_ok, "checks": checks, "feature_review": feature_review}


review_check_service = ReviewCheckService()
