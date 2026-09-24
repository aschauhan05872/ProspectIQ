"""Prospect CSV import tables.

Revision ID: 20260924_0006
Revises: 20260922_0005
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_0006"
down_revision: Union[str, None] = "20260922_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB, nullable=False),
        sa.Column("detected_headers", postgresql.JSONB, nullable=False),
        sa.Column("total_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("imported_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("dry_run", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("stored_content", sa.LargeBinary, nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_batches_tenant_id", "import_batches", ["tenant_id"])
    op.create_index("ix_import_batches_status", "import_batches", ["status"])

    op.create_table(
        "imported_prospects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id"),
            nullable=False,
        ),
        sa.Column("source_row_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolution_status", sa.String(32), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duplicate_key", sa.String(512), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("raw_data", postgresql.JSONB, nullable=False),
        sa.Column("normalized_data", postgresql.JSONB, nullable=False),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "import_batch_id",
            "source_row_number",
            name="uq_imported_prospects_tenant_batch_row",
        ),
    )
    op.create_index("ix_imported_prospects_tenant_id", "imported_prospects", ["tenant_id"])
    op.create_index("ix_imported_prospects_import_batch_id", "imported_prospects", ["import_batch_id"])
    op.create_index("ix_imported_prospects_status", "imported_prospects", ["status"])
    op.create_index("ix_imported_prospects_resolution_status", "imported_prospects", ["resolution_status"])
    op.create_index("ix_imported_prospects_company_id", "imported_prospects", ["company_id"])
    op.create_index("ix_imported_prospects_duplicate_key", "imported_prospects", ["duplicate_key"])


def downgrade() -> None:
    op.drop_table("imported_prospects")
    op.drop_table("import_batches")
