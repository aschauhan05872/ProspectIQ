"""Discovery candidate persistence and provenance.

Revision ID: 20260922_0004
Revises: 20260922_0003
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0004"
down_revision: Union[str, None] = "20260922_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("discovery_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("website_url", sa.String(2048), nullable=True),
        sa.Column("normalized_website", sa.String(2048), nullable=True),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("source_locator", sa.String(2048), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=True),
        sa.Column("provider_rank", sa.Integer(), nullable=True),
        sa.Column("field_checks", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fetch_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ingestion_status", sa.String(64), nullable=False),
        sa.Column("request_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "discovery_job_id",
            "source_locator",
            name="uq_discovery_candidates_tenant_job_locator",
        ),
    )
    op.create_index("ix_discovery_candidates_tenant_id", "discovery_candidates", ["tenant_id"])
    op.create_index(
        "ix_discovery_candidates_discovery_job_id",
        "discovery_candidates",
        ["discovery_job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_candidates_discovery_job_id", table_name="discovery_candidates")
    op.drop_index("ix_discovery_candidates_tenant_id", table_name="discovery_candidates")
    op.drop_table("discovery_candidates")
