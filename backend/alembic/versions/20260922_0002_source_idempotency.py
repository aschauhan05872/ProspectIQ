"""Company source locator uniqueness for idempotent ingestion.

Revision ID: 20260922_0002
Revises: 20260922_0001
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260922_0002"
down_revision: Union[str, None] = "20260922_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_company_sources_tenant_locator",
        "company_sources",
        ["tenant_id", "locator"],
    )
    op.create_index(
        "ix_evidence_tenant_source_locator",
        "evidence",
        ["tenant_id", "source_locator"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_tenant_source_locator", table_name="evidence")
    op.drop_constraint(
        "uq_company_sources_tenant_locator",
        "company_sources",
        type_="unique",
    )
