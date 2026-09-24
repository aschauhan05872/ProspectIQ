from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from prospectiq.domain.common import CompanyId, PersonId, TenantId, TenantScope
from prospectiq.domain.company import Company, CompanyType, Geography, Industry
from prospectiq.domain.person import DecisionFunction, Person, Seniority


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
def tenant_id() -> TenantId:
    return TenantId(UUID("00000000-0000-0000-0000-000000000001"))


@pytest.fixture
def scope(tenant_id: TenantId) -> TenantScope:
    return TenantScope(tenant_id=tenant_id, request_id="test-request")


@pytest.fixture
def matching_company(tenant_id: TenantId, now: datetime) -> Company:
    return Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_id,
        name="Example Health",
        normalized_name="example health",
        website="https://example-health.test",
        industry=Industry.HEALTHCARE_HEALTHTECH,
        geography=Geography.USA,
        employee_count=120,
        headcount_growth_pct=18.0,
        company_type=CompanyType.VENTURE_BACKED,
        is_hiring=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def matching_person(tenant_id: TenantId, matching_company: Company, now: datetime) -> Person:
    return Person(
        id=PersonId(uuid4()),
        tenant_id=tenant_id,
        company_id=matching_company.id,
        full_name="Alex Rivera",
        title="CTO",
        function=DecisionFunction.ENGINEERING,
        seniority=Seniority.CXO,
        location="Austin, TX",
        years_in_role=0.6,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    monkeypatch.setattr("prospectiq.domain.common.utcnow", lambda: now)
    monkeypatch.setattr("prospectiq.domain.jobs.utcnow", lambda: now)
    monkeypatch.setattr("prospectiq.infrastructure.jobs.utcnow", lambda: now)
