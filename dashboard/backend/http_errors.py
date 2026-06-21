"""Structured API errors for consistent frontend handling."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException


def raise_api_error(
    status_code: int,
    *,
    detail: str,
    code: Optional[str] = None,
    hint: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {"detail": detail}
    if code:
        payload["code"] = code
    if hint:
        payload["hint"] = hint
    if extra:
        payload.update(extra)
    raise HTTPException(status_code=status_code, detail=payload)
