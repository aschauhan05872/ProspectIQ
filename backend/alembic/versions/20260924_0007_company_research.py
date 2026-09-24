"""Company research cases and research pages (Phase 4).

Revision ID: 20260924_0007
Revises: 20260924_0006
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_0007"
down_revision: Union[str, None] = "20260924_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_research_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_requested", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("research_version", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message_safe", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_research_cases_tenant_id", "company_research_cases", ["tenant_id"])
    op.create_index("ix_company_research_cases_company_id", "company_research_cases", ["company_id"])
    op.create_index("ix_company_research_cases_status", "company_research_cases", ["status"])

    op.create_table(
        "research_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "research_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_research_cases.id"),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("page_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("normalized_text", sa.Text, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetch_duration_ms", sa.Integer, nullable=True),
        sa.Column("fetch_status", sa.String(32), nullable=False),
        sa.Column("failure_class", sa.String(64), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "research_case_id",
            "normalized_url",
            name="uq_research_pages_tenant_case_url",
        ),
    )
    op.create_index("ix_research_pages_tenant_id", "research_pages", ["tenant_id"])
    op.create_index("ix_research_pages_research_case_id", "research_pages", ["research_case_id"])
    op.create_index("ix_research_pages_company_id", "research_pages", ["company_id"])


def downgrade() -> None:
    op.drop_table("research_pages")
    op.drop_table("company_research_cases")
