from __future__ import annotations

from typing import Dict

from ..database import DatabaseManager


class SchemaSupportService:
    """Small helper to safely gate additive schema usage."""

    def __init__(self) -> None:
        self._table_cache: Dict[str, bool] = {}
        self._column_cache: Dict[str, bool] = {}

    async def table_exists(
        self,
        db: DatabaseManager,
        table: str,
        schema: str = "main",
    ) -> bool:
        cache_key = f"{schema}.{table}"
        if cache_key in self._table_cache:
            return self._table_cache[cache_key]

        found = await db.fetch_val(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = $1
                  AND table_name = $2
            )
            """,
            schema,
            table,
        )
        value = bool(found)
        self._table_cache[cache_key] = value
        return value

    async def column_exists(
        self,
        db: DatabaseManager,
        table: str,
        column: str,
        schema: str = "main",
    ) -> bool:
        cache_key = f"{schema}.{table}.{column}"
        if cache_key in self._column_cache:
            return self._column_cache[cache_key]

        found = await db.fetch_val(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name = $2
                  AND column_name = $3
            )
            """,
            schema,
            table,
            column,
        )
        value = bool(found)
        self._column_cache[cache_key] = value
        return value

    def clear_cache(self) -> None:
        self._table_cache.clear()
        self._column_cache.clear()


schema_support = SchemaSupportService()
