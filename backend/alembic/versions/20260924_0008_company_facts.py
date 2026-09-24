"""Structured company facts from research evidence (Phase 5).

Revision ID: 20260924_0008
Revises: 20260924_0007
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_0008"
down_revision: Union[str, None] = "20260924_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "research_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_research_cases.id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("extraction_method", sa.String(64), nullable=False),
        sa.Column("extraction_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("dedupe_key", sa.String(64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "research_case_id",
            "dedupe_key",
            name="uq_company_facts_tenant_case_dedupe",
        ),
    )
    op.create_index("ix_company_facts_tenant_id", "company_facts", ["tenant_id"])
    op.create_index("ix_company_facts_company_id", "company_facts", ["company_id"])
    op.create_index("ix_company_facts_research_case_id", "company_facts", ["research_case_id"])
    op.create_index("ix_company_facts_category", "company_facts", ["category"])


def downgrade() -> None:
    op.drop_table("company_facts")
