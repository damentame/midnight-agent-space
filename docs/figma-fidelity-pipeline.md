# Figma Fidelity Pipeline — Current vs Target State

Canonical reference for the design-to-code pipeline upgrade. See also [mas-stabilization-and-ux-plan.md](./mas-stabilization-and-ux-plan.md) for broader MAS stabilization context.

---

## Current state (v1)

| Layer | Behavior |
|-------|----------|
| **Figma import** | REST API only; compact tree capped at 96 nodes, depth 3; boxes store `w`/`h` only (no `x`/`y`); text truncated to 200 chars; max 6 PNG exports |
| **Assets** | `fillType: IMAGE` noted in spec but no image bytes exported; agents substitute stock photos |
| **DB** | One `figma_import` row + orphan `figma_export_image` rows; no `parent_document_id`; re-import appends and overwrites staged files |
| **Staging** | `.midnight/design/` with flat `figma-spec.json`, `figma-spec.md`, `exports/frame-N.png`, `DESIGN_MANIFEST.md` |
| **Context pack** | `figma_spec_excerpt` capped at 1200 chars; pinned Figma doc up to 4000 chars |
| **Agent tasks** | 4 generic tasks (analyze, plan, implement, review); single implementation pass |
| **Verification** | `review_check_service` checks design refs exist; no structural or visual fidelity gate |
| **Temporal** | Text-only RAG from `raw_text_content`; PNGs and section manifests not chunked |
| **UI** | Import form only; no section tree, asset status, or pre-execute readiness |

**Observed failure mode:** Agents build a thematically similar landing page (Unsplash images, guessed fonts/SVGs) instead of matching the Figma frame.

---

## Target state (v2)

| Layer | Behavior |
|-------|----------|
| **Figma import** | Section-scoped full trees (up to 500 nodes/section); boxes include `x`, `y`, `w`, `h`; gradients, effects, corner radius; auto-slice tall frames into viewport bands |
| **Assets** | All IMAGE/VECTOR nodes exported via Figma images API; staged as `figma_asset` child docs and `assets/` in worktree |
| **DB** | Parent `figma_import` with linked children via `parent_document_id`; supersede prior import for same `node_id`; `agent_context` v2 schema |
| **Staging** | `sections/{slug}.json` + `{slug}.png`, `assets/`, `tokens.css`, `ASSET_MANIFEST.json`, enhanced `DESIGN_MANIFEST.md` |
| **Context pack** | Per-section context for implementation tasks (up to 8000 chars/section); active import only |
| **Agent tasks** | Per-section implementation tasks + integrate + review; `design_section_slug` in task metadata |
| **Verification** | Structural hard gate (no stock photos, assets referenced, tokens used); advisory visual diff per section |
| **Temporal** | Section manifest text chunked; design staging hook before implementation tasks |
| **UI** | `FigmaDesignStatus` panel, design-readiness API, Execute guard, RunDetail fidelity panel |

---

## Removed

- Global 96-node cap as the binding design spec for implementation
- `FIGMA_SPEC_CONTEXT_LIMIT = 1200` for implementation/review tasks
- Orphan export rows without parent linkage
- Silent multi-import overwrite of staged worktree files
- Success criterion of "app runs" without structural design checks

---

## Added

| Item | Location |
|------|----------|
| `agent_context` v2 schema | `structured_json` on `figma_import` |
| Document types `figma_asset`, `figma_section_export` | `project_document.document_type` |
| `figma_font_service.py` | Google Fonts mapping |
| `design_fidelity_service.py` | Structural + advisory visual checks |
| `tokens.css`, `ASSET_MANIFEST.json` | `.midnight/design/` |
| `GET /api/projects/{id}/design-readiness` | API |
| `POST /api/projects/{id}/figma/reimport` | API |
| `FigmaDesignStatus` component | Frontend |
| `phase12_figma_fidelity.sql` | DB index for active imports |
| Config env vars | `FIGMA_MAX_SECTION_NODES`, `DESIGN_FIDELITY_*`, etc. |

---

## How each layer changes

### 1. DB (`project_document`, `project_metadata`)

- `insert_document_upload` accepts `parent_document_id`
- `deactivate_figma_import_family()` marks prior import tree inactive
- `figma_source` metadata extended: `extraction_version`, `section_count`, `asset_count`, `active_document_id`

### 2. Import (`figma_service.py`, `figma_handlers.py`)

- `fetch_design` returns v2 payload: sections, assets, tokens, warnings
- Child docs created for each section PNG and asset
- Import response includes section/asset inventory

### 3. Staging (`design_context_service.py`)

- Writes section-scoped files, asset bundle, tokens CSS, asset manifest
- `validate_design_context` v2 checks sections, assets, blocking warnings

### 4. Context pack (`context_pack_service.py`)

- Section-scoped compact for implementation tasks
- Active import filtering; child doc pinning via parent link

### 5. Run orchestration (`run_service.py`, `projects.py`)

- Section-based task decomposition when Figma present
- Structural fidelity gate after implementation (hard block)
- Advisory visual diff scores in `result_payload.design_fidelity`

### 6. Verification (`review_check_service.py`, `design_fidelity_service.py`)

- New checks: `stock_photos_absent`, `design_assets_used`, `sections_implemented`, `visual_fidelity_scored`
- `design_gaps_blocking` true only on structural failures

### 7. Temporal (`chunking.py`, `task_execution_activities.py`)

- Chunk `sections[].manifest_text` + tokens summary for RAG
- Stage design context before implementation tasks when worktree available

### 8. UI (`ProjectDetail.tsx`, `RunDetail.tsx`, `FigmaDesignStatus.tsx`)

- Design readiness before Execute
- Section tree and import warnings on Context tab
- Fidelity results on Run detail

---

## Staged worktree layout (v2)

```
.midnight/design/
  DESIGN_MANIFEST.md
  ASSET_MANIFEST.json
  tokens.css
  figma-spec.json
  figma-spec.md
  sections/
    hero.json
    hero.png
    menu-brand.json
    menu-brand.png
  assets/
    1177-18357.png
    1026-19533.svg
  exports/          # legacy compat copies
```

---

## Fidelity gates

| Gate | Severity | Blocks completion? |
|------|----------|-------------------|
| Missing `node-id` | Warning | No (unless `FIGMA_REQUIRE_NODE_ID=true`) |
| Zero assets on IMAGE-heavy design | Warning | No |
| Stock photo URLs in code | Error | **Yes** |
| Asset manifest nodes not referenced | Error | **Yes** |
| Missing section DOM landmarks | Error | **Yes** |
| Visual pixel diff score | Advisory | No (v1) |

---

## `agent_context` v2 schema

```json
{
  "extraction_version": "v2",
  "sections": [
    {
      "slug": "hero",
      "name": "Hero",
      "node_id": "1026:19508",
      "box": { "x": 0, "y": 0, "w": 1920, "h": 814 },
      "node_count": 42,
      "manifest_text": "...",
      "section_export_document_id": 123
    }
  ],
  "assets": [
    {
      "node_id": "1177:18357",
      "document_id": 124,
      "filename": "1177-18357.png",
      "section_slug": "hero",
      "asset_type": "IMAGE"
    }
  ],
  "tokens": {
    "colors": { "--color-primary": "#daccb2" },
    "typography": { "--font-display": "Bebas Neue" },
    "spacing": { "--spacing-md": "32px" }
  },
  "compact_spec": { "tree": "..." },
  "section_export_document_ids": [],
  "asset_document_ids": [],
  "image_document_ids": [],
  "extraction_warnings": [],
  "extraction_status": "figma_api_v2_ready"
}
```
