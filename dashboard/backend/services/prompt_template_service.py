from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class PromptTemplateService:
    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / "agent_assets"
        self._prompts_dir = base_dir / "prompts"
        self._schemas_dir = base_dir / "schemas"

    def list_prompt_templates(self) -> List[str]:
        if not self._prompts_dir.exists():
            return []
        return sorted([p.stem for p in self._prompts_dir.glob("*.md")])

    def load_prompt_template(self, template_name: str) -> str:
        path = self._prompts_dir / f"{template_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_name}")
        return path.read_text(encoding="utf-8")

    def list_json_schemas(self) -> List[str]:
        if not self._schemas_dir.exists():
            return []
        return sorted([p.stem for p in self._schemas_dir.glob("*.json")])

    def load_json_schema(self, schema_name: str) -> Dict[str, Any]:
        path = self._schemas_dir / f"{schema_name}.json"
        if not path.exists():
            raise FileNotFoundError(f"JSON schema not found: {schema_name}")
        return json.loads(path.read_text(encoding="utf-8"))


prompt_template_service = PromptTemplateService()
