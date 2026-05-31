from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Mapping


def jsonb_dumps(value: Any) -> Any:
    """Serialize dict/list values for asyncpg JSONB bindings."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return value


def decode_json_if_needed(value: Any) -> Any:
    """Decode JSON text values while leaving other types unchanged."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def decode_jsonb_fields(record: Mapping[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    data = dict(record)
    for field in fields:
        if field in data:
            data[field] = decode_json_if_needed(data.get(field))
    return data
