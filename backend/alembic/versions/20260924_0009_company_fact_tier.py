"""Add fact_tier to company_facts (Phase 5 remediation).

Revision ID: 20260924_0009
Revises: 20260924_0008
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0009"
down_revision: Union[str, None] = "20260924_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_facts",
        sa.Column("fact_tier", sa.String(32), nullable=False, server_default="substantive"),
    )
    op.execute(
        """
        UPDATE company_facts
        SET fact_tier = 'metadata'
        WHERE subject IN ('page_classification', 'page_title')
        """
    )
    op.alter_column("company_facts", "fact_tier", server_default=None)


def downgrade() -> None:
    op.drop_column("company_facts", "fact_tier")
