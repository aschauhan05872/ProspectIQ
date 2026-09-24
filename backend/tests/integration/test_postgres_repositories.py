"""Phase 1: real repository persistence against PostgreSQL."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.conftest import NOW, TENANT_B

from prospectiq.domain.common import CompanyId, Confidence, EvidenceId, TenantId
from prospectiq.domain.company import Company
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.signal import Signal, SignalId, SignalType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemySignalRepository,
)


@pytest.mark.integration
async def test_company_and_evidence_persistence(
    db_session: AsyncSession,
    tenant_scope: object,
) -> None:
    companies = SqlAlchemyCompanyRepository(db_session)
    evidence_repo = SqlAlchemyEvidenceRepository(db_session)
    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        name="Acme Health",
        normalized_name="acme-health.test",
        website="https://acme-health.test",
        industry=None,
        geography=None,
        employee_count=120,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(tenant_scope, company)  # type: ignore[arg-type]
    item = Evidence(
        id=EvidenceId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        fact="We are hiring a Software Engineer.",
        origin=EvidenceOrigin.SOURCE_DERIVED,
        source_class=SourceClass.CAREERS_PAGE,
        source_locator="https://acme-health.test/careers",
        collected_at=NOW,
        confidence=Confidence.HIGH,
        snippet="hiring",
        company_id=company.id,
        metadata={"fact_kind": "page_content"},
    )
    await evidence_repo.add(tenant_scope, item)  # type: ignore[arg-type]
    stored = await evidence_repo.list_for_company(tenant_scope, company.id)  # type: ignore[arg-type]
    assert len(stored) == 1
    await db_session.commit()


@pytest.mark.integration
async def test_signal_upsert_is_idempotent_by_type(
    db_session: AsyncSession,
    tenant_scope: object,
) -> None:
    companies = SqlAlchemyCompanyRepository(db_session)
    signals = SqlAlchemySignalRepository(db_session)
    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        name="Signal Co",
        normalized_name="signal-co.test",
        website="https://signal-co.test",
        industry=None,
        geography=None,
        employee_count=None,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(tenant_scope, company)  # type: ignore[arg-type]
    evidence_id = EvidenceId(uuid4())
    evidence_repo = SqlAlchemyEvidenceRepository(db_session)
    await evidence_repo.add(  # type: ignore[arg-type]
        tenant_scope,
        Evidence(
            id=evidence_id,
            tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
            fact="We are hiring a Software Engineer.",
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=SourceClass.CAREERS_PAGE,
            source_locator="https://signal-co.test/careers",
            collected_at=NOW,
            confidence=Confidence.HIGH,
            snippet="hiring",
            company_id=company.id,
            metadata={"fact_kind": "page_content"},
        ),
    )
    first = Signal(
        id=SignalId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        signal_type=SignalType.HIRING_TECH_ROLES,
        weight=3,
        detected_at=NOW,
        evidence_id=evidence_id,
        company_id=company.id,
        reason="first",
    )
    second = Signal(
        id=SignalId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        signal_type=SignalType.HIRING_TECH_ROLES,
        weight=3,
        detected_at=NOW,
        evidence_id=evidence_id,
        company_id=company.id,
        reason="second",
    )
    saved_first = await signals.upsert(tenant_scope, first)  # type: ignore[arg-type]
    saved_second = await signals.upsert(tenant_scope, second)  # type: ignore[arg-type]
    assert saved_first.id == saved_second.id
    rows = await signals.list_for_company(tenant_scope, company.id)  # type: ignore[arg-type]
    assert len(rows) == 1
    await db_session.commit()


@pytest.mark.integration
async def test_tenant_isolation_on_company_read(
    db_session: AsyncSession,
    tenant_scope: object,
) -> None:
    companies = SqlAlchemyCompanyRepository(db_session)
    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        name="Private",
        normalized_name="private.test",
        website="https://private.test",
        industry=None,
        geography=None,
        employee_count=None,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(tenant_scope, company)  # type: ignore[arg-type]
    from prospectiq.domain.common import TenantScope

    other_scope = TenantScope(tenant_id=TenantId(TENANT_B))
    assert await companies.get(other_scope, company.id) is None
    await db_session.commit()
