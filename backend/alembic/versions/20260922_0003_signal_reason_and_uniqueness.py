"""Signal provenance reason and one current signal per company type.

Revision ID: 20260922_0003
Revises: 20260922_0002
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0003"
down_revision: Union[str, None] = "20260922_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("reason", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_signals_tenant_company_type",
        "signals",
        ["tenant_id", "company_id", "signal_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_signals_tenant_company_type",
        "signals",
        type_="unique",
    )
    op.drop_column("signals", "reason")
