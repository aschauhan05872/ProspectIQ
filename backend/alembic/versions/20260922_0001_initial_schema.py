"""Initial tenant-scoped schema.

Revision ID: 20260922_0001
Revises:
Create Date: 2026-09-22
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INTERNAL_TENANT = UUID("00000000-0000-0000-0000-000000000001")
INTERNAL_WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
INTERNAL_USER = UUID("00000000-0000-0000-0000-000000000003")


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspaces_tenant_id", "workspaces", ["tenant_id"])
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_table(
        "search_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filters_json", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_profiles_tenant_id", "search_profiles", ["tenant_id"])
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("website", sa.String(1024), nullable=True),
        sa.Column("industry", sa.String(128), nullable=True),
        sa.Column("geography", sa.String(64), nullable=True),
        sa.Column("employee_count", sa.Integer, nullable=True),
        sa.Column("headcount_growth_pct", sa.Float, nullable=True),
        sa.Column("company_type", sa.String(64), nullable=True),
        sa.Column("is_hiring", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "normalized_name", name="uq_companies_tenant_name"),
    )
    op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])
    op.create_table(
        "company_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("source_class", sa.String(64), nullable=False),
        sa.Column("locator", sa.String(2048), nullable=False),
        sa.Column("raw_reference", sa.Text, nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_sources_tenant_id", "company_sources", ["tenant_id"])
    op.create_table(
        "persons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("function", sa.String(64), nullable=True),
        sa.Column("seniority", sa.String(64), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("years_in_role", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_persons_tenant_id", "persons", ["tenant_id"])
    op.create_table(
        "person_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("source_class", sa.String(64), nullable=False),
        sa.Column("locator", sa.String(2048), nullable=False),
        sa.Column("raw_reference", sa.Text, nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_person_sources_tenant_id", "person_sources", ["tenant_id"])
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fact", sa.Text, nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("source_class", sa.String(64), nullable=True),
        sa.Column("source_locator", sa.String(2048), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("snippet", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_evidence_tenant_id", "evidence", ["tenant_id"])
    op.create_index("ix_evidence_lead_id", "evidence", ["lead_id"])
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("weight", sa.Integer, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence.id"), nullable=False),
    )
    op.create_index("ix_signals_tenant_id", "signals", ["tenant_id"])
    op.create_index("ix_signals_lead_id", "signals", ["lead_id"])
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id"), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("is_qualified", sa.Boolean, nullable=False),
        sa.Column("search_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_table(
        "lead_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("total_score", sa.Integer, nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("is_qualified", sa.Boolean, nullable=False),
        sa.Column("distinct_buying_signals", sa.Integer, nullable=False),
        sa.Column("breakdown", postgresql.JSONB, nullable=False),
        sa.Column("ruleset_version", sa.String(64), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lead_scores_tenant_id", "lead_scores", ["tenant_id"])
    op.create_index("ix_lead_scores_lead_id", "lead_scores", ["lead_id"])
    op.create_table(
        "research_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_research_runs_tenant_id", "research_runs", ["tenant_id"])
    op.create_table(
        "message_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("draft_type", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_message_drafts_tenant_id", "message_drafts", ["tenant_id"])
    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("activity_type", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_activities_tenant_id", "activities", ["tenant_id"])
    op.create_index("ix_activities_lead_id", "activities", ["lead_id"])
    op.create_table(
        "follow_up_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("earliest_date", sa.Date, nullable=False),
        sa.Column("latest_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("cancelled_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_follow_up_tasks_tenant_id", "follow_up_tasks", ["tenant_id"])
    op.create_index("ix_follow_up_tasks_lead_id", "follow_up_tasks", ["lead_id"])
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_table(
        "source_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("source_class", sa.String(64), nullable=False),
        sa.Column("is_permitted", sa.Boolean, nullable=False),
        sa.Column("requires_official_integration", sa.Boolean, nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_policies_tenant_id", "source_policies", ["tenant_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("max_attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_jobs_tenant_idempotency"),
    )
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    now = datetime.now(timezone.utc)
    tenants = sa.table(
        "tenants",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    workspaces = sa.table(
        "workspaces",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    users = sa.table(
        "users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("email", sa.String),
        sa.column("display_name", sa.String),
        sa.column("role", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        tenants,
        [
            {
                "id": INTERNAL_TENANT,
                "name": "ProspectIQ Internal",
                "slug": "internal",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.bulk_insert(
        workspaces,
        [
            {
                "id": INTERNAL_WORKSPACE,
                "tenant_id": INTERNAL_TENANT,
                "name": "Internal Sales",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.bulk_insert(
        users,
        [
            {
                "id": INTERNAL_USER,
                "tenant_id": INTERNAL_TENANT,
                "email": "internal@prospectiq.local",
                "display_name": "Internal Operator",
                "role": "admin",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    policies = sa.table(
        "source_policies",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("source_class", sa.String),
        sa.column("is_permitted", sa.Boolean),
        sa.column("requires_official_integration", sa.Boolean),
        sa.column("notes", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    from uuid import uuid4

    source_rows = [
        ("company_website", True, False, "Public company website content."),
        ("careers_page", True, False, "Public careers/jobs pages."),
        ("public_announcement", True, False, "Public company announcements."),
        ("public_news", True, False, "Public news sources."),
        ("public_funding", True, False, "Public funding/news sources."),
        ("permitted_search_api", True, False, "Explicitly permitted search/data APIs."),
        ("licensed_data_provider", True, False, "Licensed business-information providers."),
        (
            "official_linkedin",
            False,
            True,
            "Official LinkedIn API only when authorized.",
        ),
    ]
    op.bulk_insert(
        policies,
        [
            {
                "id": uuid4(),
                "tenant_id": None,
                "source_class": source_class,
                "is_permitted": permitted,
                "requires_official_integration": official,
                "notes": notes,
                "created_at": now,
            }
            for source_class, permitted, official, notes in source_rows
        ],
    )


def downgrade() -> None:
    for table in (
        "jobs",
        "audit_events",
        "source_policies",
        "notifications",
        "follow_up_tasks",
        "activities",
        "message_drafts",
        "research_runs",
        "lead_scores",
        "leads",
        "signals",
        "evidence",
        "person_sources",
        "persons",
        "company_sources",
        "companies",
        "search_profiles",
        "users",
        "workspaces",
        "tenants",
    ):
        op.drop_table(table)
