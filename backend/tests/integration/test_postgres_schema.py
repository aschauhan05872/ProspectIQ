"""Phase 1: migration and schema availability."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_schema_tables_exist(db_session: AsyncSession, migrated_schema: None) -> None:
    def _tables(sync_conn: object) -> set[str]:
        return set(inspect(sync_conn).get_table_names())  # type: ignore[arg-type]

    conn = await db_session.connection()
    tables = await conn.run_sync(_tables)
    required = {
        "tenants",
        "workspaces",
        "companies",
        "company_sources",
        "evidence",
        "signals",
        "leads",
        "jobs",
        "discovery_candidates",
    }
    missing = required - tables
    assert not missing, f"Missing tables: {missing}"


@pytest.mark.integration
async def test_jsonb_and_constraints(db_session: AsyncSession, migrated_schema: None) -> None:
    row = await db_session.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'discovery_candidates'
              AND column_name IN ('field_checks', 'source_evidence_ids', 'request_snapshot')
            """
        )
    )
    types = {item[0]: item[1] for item in row.fetchall()}
    assert types["field_checks"] == "jsonb"
    assert types["source_evidence_ids"] == "jsonb"
    assert types["request_snapshot"] == "jsonb"
