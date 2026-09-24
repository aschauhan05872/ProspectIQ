"""Pipeline linkage fields on discovery candidates.

Revision ID: 20260922_0005
Revises: 20260922_0004
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0005"
down_revision: Union[str, None] = "20260922_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("research_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "discovery_candidates",
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "discovery_candidates",
        sa.Column(
            "source_evidence_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_discovery_candidates_fetch_job_id",
        "discovery_candidates",
        ["fetch_job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_candidates_fetch_job_id", table_name="discovery_candidates")
    op.drop_column("discovery_candidates", "source_evidence_ids")
    op.drop_column("discovery_candidates", "lead_id")
    op.drop_column("discovery_candidates", "research_job_id")
