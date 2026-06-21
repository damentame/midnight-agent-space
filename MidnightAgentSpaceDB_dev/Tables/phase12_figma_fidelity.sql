-- Phase 12: Figma fidelity pipeline (uses existing project_document columns)
-- Document types: figma_import, figma_section_export, figma_asset, figma_export_image (legacy)
-- parent_document_id links child exports/assets to active figma_import parent.

CREATE INDEX IF NOT EXISTS idx_project_document_active_figma
    ON main.project_document USING btree
    (project_id ASC NULLS LAST, document_type COLLATE pg_catalog."default" ASC NULLS LAST)
    WHERE COALESCE(is_active_version, true) = true
    AND document_type IN ('figma_import', 'figma_section_export', 'figma_asset', 'figma_export_image');
