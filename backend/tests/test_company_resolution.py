"""Unit tests for company resolution from imported prospects."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from prospectiq.application.company_resolution import CompanyResolutionService
from prospectiq.domain.common import ImportBatchId, ImportedProspectId, TenantId, TenantScope
from prospectiq.domain.company_resolution import plan_company_resolution
from prospectiq.domain.prospect_import import (
    ImportedProspect,
    ImportedProspectStatus,
    ResolutionStatus,
)
from tests.fakes import (
    InMemoryCompanyRepository,
    InMemoryImportedProspectRepository,
    InMemoryPersonRepository,
)

TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _scope() -> TenantScope:
    return TenantScope(tenant_id=TENANT)


def _prospect(**overrides: object) -> ImportedProspect:
    normalized: dict[str, object] = {
        "company_name": "Acme Inc",
        "company_domain": "acme.test",
        "website": "https://acme.test",
        "full_name": "Jane Doe",
        "job_title": "CTO",
        "email": "jane@acme.test",
    }
    normalized.update(overrides)
    return ImportedProspect(
        id=ImportedProspectId(uuid4()),
        tenant_id=TENANT,
        import_batch_id=ImportBatchId(uuid4()),
        source_row_number=2,
        status=ImportedProspectStatus.IMPORTED,
        resolution_status=ResolutionStatus.PENDING,
        company_id=None,
        person_id=None,
        duplicate_of_id=None,
        duplicate_key="email:jane@acme.test",
        error_message=None,
        raw_data={},
        normalized_data=normalized,
        provider="test",
        created_at=NOW,
        updated_at=NOW,
    )


def test_plan_resolves_by_domain() -> None:
    plan = plan_company_resolution({"company_domain": "stripe.com"})
    assert plan.status is ResolutionStatus.RESOLVED
    assert plan.normalized_domain == "stripe.com"


def test_plan_manual_review_without_domain() -> None:
    plan = plan_company_resolution({"company_name": "Mystery Corp"})
    assert plan.status is ResolutionStatus.MANUAL_REVIEW


@pytest.mark.asyncio
async def test_resolve_batch_deduplicates_company_research() -> None:
    companies = InMemoryCompanyRepository()
    persons = InMemoryPersonRepository()
    prospects_repo = InMemoryImportedProspectRepository()
    service = CompanyResolutionService(
        companies=companies, persons=persons, prospects=prospects_repo
    )
    p1 = _prospect(full_name="Jane Doe", email="jane@acme.test")
    p2 = _prospect(full_name="John Smith", email="john@acme.test")
    p2.normalized_data["full_name"] = "John Smith"
    p2.normalized_data["email"] = "john@acme.test"
    p2.duplicate_key = "email:john@acme.test"
    p2.id = ImportedProspectId(uuid4())
    await prospects_repo.create(_scope(), p1)
    await prospects_repo.create(_scope(), p2)

    stats = await service.resolve_batch(_scope(), [p1, p2])
    assert stats["resolved"] == 2
    assert stats["skipped"] == 0
    assert len(companies.items) == 1
    assert len(persons.items) == 2
    assert p1.company_id is not None
    assert p2.company_id == p1.company_id
