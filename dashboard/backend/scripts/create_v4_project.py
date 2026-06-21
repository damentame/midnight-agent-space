"""One-off script: create the V4 landing page test project.

Creates a fresh git-backed project workspace, registers it in the database
with a text brief, and pre-sets `runtime_preferences.execution_mode =
"milestones"` so the milestone-based execution flow can be exercised end to
end from the dashboard UI (Serialize -> Analysis Plan -> Execute).

Run with: python -m dashboard.backend.scripts.create_v4_project
"""
from __future__ import annotations

import asyncio

from dashboard.backend.database import DatabaseManager
from dashboard.backend.services.project_metadata_service import project_metadata_service
from dashboard.backend.services.repo_workspace_service import repo_workspace_service

PROJECT_NAME = "V4 Landing Page"

PROJECT_BRIEF = """# V4 Landing Page

Build a single-page marketing landing page for a product launch with the
following sections, in order:

1. **Navbar** - logo/wordmark on the left, nav links (Home, About, Products,
   Contact) on the right, with a prominent "Get Started" call-to-action
   button.
2. **Hero** - large headline, supporting subheading, primary call-to-action
   button, and a hero image or illustration placeholder.
3. **About** - short company/product story with a heading, body copy, and a
   supporting image or stats row.
4. **Products Showcase** - a grid or carousel of product cards, each with an
   image, title, short description, and price/CTA.
5. **Footer** - column layout with company info, quick links, social icons,
   and a copyright line.
6. **CTA** - a final full-width call-to-action band encouraging signup, with
   a heading, short supporting copy, and a button.

Use a clean, modern visual style with consistent spacing, typography, and
color palette across all sections. Sections should be responsive (mobile,
tablet, desktop)."""


async def main() -> None:
    workspace = await repo_workspace_service.prepare_workspace(
        parent_path=None,
        project_name=PROJECT_NAME,
        mode="create",
    )
    if not workspace.get("ok"):
        raise RuntimeError(f"failed to create workspace: {workspace.get('error')}")
    repo_path = workspace["repo_path"]

    db = DatabaseManager()
    await db.initialize()
    try:
        project = await db.insert_project(
            project_name=PROJECT_NAME,
            project_type="Web App",
            description="Single-page marketing landing page (Navbar, Hero, About, Products Showcase, Footer, CTA).",
            status="ACTIVE",
        )
        project_id = project["project_id"]

        brief_bytes = PROJECT_BRIEF.encode("utf-8")
        await db.insert_document_upload(
            project_id,
            document_name="Project Brief",
            document_type="text",
            raw_text=PROJECT_BRIEF,
            ext=".md",
            mime="text/markdown",
            size=len(brief_bytes),
            file_bytes=None,
        )

        await project_metadata_service.update_project_metadata(
            db,
            project_id,
            repository_url=repo_path,
            default_branch="main",
            runtime_preferences={
                "repo_path": repo_path,
                "execution_mode": "milestones",
            },
        )
    finally:
        await db.close()

    print(f"Created project_id={project_id} ({PROJECT_NAME})")
    print(f"Repo path: {repo_path}")
    print("runtime_preferences.execution_mode = milestones")
    print()
    print("Next steps (in the dashboard UI):")
    print(f"  1. Open project {project_id}")
    print("  2. Serialize the project brief document")
    print("  3. Generate the analysis plan (milestones will be assigned automatically)")
    print("  4. Execute (Quick Run) and watch the progress dashboard")


if __name__ == "__main__":
    asyncio.run(main())
