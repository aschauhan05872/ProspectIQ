"""Tenant-scoped repositories. Queries always include tenant_id."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.domain.common import (
    CompanyFactId,
    CompanyId,
    Confidence,
    EvidenceId,
    ImportBatchId,
    ImportedProspectId,
    JobId,
    LeadId,
    PersonId,
    SignalId,
    TenantId,
    TenantScope,
)
from prospectiq.domain.company import Company, CompanySource, CompanyType, Geography, Industry
from prospectiq.domain.company_facts import (
    CompanyFact,
    CompanyFactCategory,
    CompanyFactStatus,
    CompanyFactTier,
)
from prospectiq.domain.company_research import (
    CompanyResearchCase,
    CompanyResearchStatus,
    ResearchErrorCode,
    ResearchPage,
    ResearchPageFetchStatus,
    ResearchPageType,
)
from prospectiq.domain.discovery import DiscoveryCandidate, DiscoveryIngestionStatus
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.lead import Lead, LeadScoreRecord
from prospectiq.domain.person import DecisionFunction, Person, Seniority
from prospectiq.domain.pipeline import LeadStatus
from prospectiq.domain.prospect_import import (
    ImportBatch,
    ImportBatchStatus,
    ImportedProspect,
    ImportedProspectStatus,
    ResolutionStatus,
)
from prospectiq.domain.scoring import LeadClassification
from prospectiq.domain.signal import Signal, SignalType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.models import (
    CompanyFactRow,
    CompanyResearchCaseRow,
    CompanyRow,
    CompanySourceRow,
    DiscoveryCandidateRow,
    EvidenceRow,
    ImportBatchRow,
    ImportedProspectRow,
    LeadRow,
    LeadScoreRow,
    PersonRow,
    ResearchPageRow,
    SignalRow,
)


class TenantMismatchError(Exception):
    pass


def _require_scope(scope: TenantScope, tenant_id: UUID) -> None:
    if UUID(str(scope.tenant_id)) != tenant_id:
        raise TenantMismatchError("Refusing to persist a record outside the tenant scope.")


class SqlAlchemyCompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scope: TenantScope, company_id: CompanyId) -> Company | None:
        row = await self._session.get(CompanyRow, company_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _company_from_row(row)

    async def get_by_normalized_name(
        self, scope: TenantScope, normalized_name: str
    ) -> Company | None:
        stmt = select(CompanyRow).where(
            CompanyRow.tenant_id == scope.tenant_id,
            CompanyRow.normalized_name == normalized_name,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _company_from_row(row) if row else None

    async def upsert(self, scope: TenantScope, company: Company) -> Company:
        _require_scope(scope, company.tenant_id)
        row = await self._session.get(CompanyRow, company.id)
        if row is None:
            row = CompanyRow(id=company.id, tenant_id=company.tenant_id)
            self._session.add(row)
        elif row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Company belongs to another tenant.")
        row.name = company.name
        row.normalized_name = company.normalized_name
        row.website = company.website
        row.industry = company.industry.value if company.industry else None
        row.geography = company.geography.value if company.geography else None
        row.employee_count = company.employee_count
        row.headcount_growth_pct = company.headcount_growth_pct
        row.company_type = company.company_type.value if company.company_type else None
        row.is_hiring = company.is_hiring
        row.created_at = company.created_at
        row.updated_at = company.updated_at
        return company


class SqlAlchemyCompanySourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_locator(self, scope: TenantScope, locator: str) -> CompanySource | None:
        stmt = select(CompanySourceRow).where(
            CompanySourceRow.tenant_id == scope.tenant_id,
            CompanySourceRow.locator == locator,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _company_source_from_row(row) if row else None

    async def upsert(self, scope: TenantScope, source: CompanySource) -> CompanySource:
        _require_scope(scope, source.tenant_id)
        existing = await self.get_by_locator(scope, source.locator)
        if existing is not None and existing.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Company source belongs to another tenant.")
        row = None
        if existing is not None:
            row = await self._session.get(CompanySourceRow, existing.id)
        if row is None:
            row = CompanySourceRow(id=source.id, tenant_id=source.tenant_id)
            self._session.add(row)
        elif row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Company source belongs to another tenant.")
        row.company_id = source.company_id
        row.source_class = source.source_class.value
        row.locator = source.locator
        row.raw_reference = source.raw_reference
        row.collected_at = source.collected_at
        return CompanySource(
            id=row.id,
            tenant_id=source.tenant_id,
            company_id=source.company_id,
            source_class=source.source_class,
            locator=source.locator,
            raw_reference=source.raw_reference,
            collected_at=source.collected_at,
        )


class SqlAlchemyPersonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scope: TenantScope, person_id: PersonId) -> Person | None:
        row = await self._session.get(PersonRow, person_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _person_from_row(row)

    async def upsert(self, scope: TenantScope, person: Person) -> Person:
        _require_scope(scope, person.tenant_id)
        row = await self._session.get(PersonRow, person.id)
        if row is None:
            row = PersonRow(id=person.id, tenant_id=person.tenant_id)
            self._session.add(row)
        elif row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Person belongs to another tenant.")
        row.company_id = person.company_id
        row.full_name = person.full_name
        row.title = person.title
        row.function = person.function.value if person.function else None
        row.seniority = person.seniority.value if person.seniority else None
        row.location = person.location
        row.years_in_role = person.years_in_role
        row.created_at = person.created_at
        row.updated_at = person.updated_at
        return person


class SqlAlchemyLeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scope: TenantScope, lead_id: LeadId) -> Lead | None:
        row = await self._session.get(LeadRow, lead_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _lead_from_row(row)

    async def list_for_workspace(
        self,
        scope: TenantScope,
        *,
        limit: int = 50,
        offset: int = 0,
        is_qualified: bool | None = None,
        classification: str | None = None,
    ) -> list[Lead]:
        stmt = (
            select(LeadRow)
            .where(LeadRow.tenant_id == scope.tenant_id)
            .order_by(LeadRow.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if scope.workspace_id is not None:
            stmt = stmt.where(LeadRow.workspace_id == scope.workspace_id)
        if is_qualified is not None:
            stmt = stmt.where(LeadRow.is_qualified.is_(is_qualified))
        if classification is not None:
            stmt = stmt.where(LeadRow.classification == classification)
        result = await self._session.execute(stmt)
        return [_lead_from_row(row) for row in result.scalars().all()]

    async def get_by_company(self, scope: TenantScope, company_id: CompanyId) -> Lead | None:
        stmt = (
            select(LeadRow)
            .where(
                LeadRow.tenant_id == scope.tenant_id,
                LeadRow.company_id == company_id,
                LeadRow.person_id.is_(None),
            )
            .order_by(LeadRow.updated_at.desc())
            .limit(1)
        )
        if scope.workspace_id is not None:
            stmt = stmt.where(LeadRow.workspace_id == scope.workspace_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _lead_from_row(row) if row else None

    async def upsert(self, scope: TenantScope, lead: Lead) -> Lead:
        _require_scope(scope, lead.tenant_id)
        row = await self._session.get(LeadRow, lead.id)
        if row is None:
            row = LeadRow(id=lead.id, tenant_id=lead.tenant_id)
            self._session.add(row)
        elif row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Lead belongs to another tenant.")
        row.workspace_id = lead.workspace_id
        row.company_id = lead.company_id
        row.person_id = lead.person_id
        row.status = lead.status.value
        row.score = lead.score
        row.classification = lead.classification.value
        row.is_qualified = lead.is_qualified
        row.search_profile_id = lead.search_profile_id
        row.created_at = lead.created_at
        row.updated_at = lead.updated_at
        return lead

    async def save_score(self, scope: TenantScope, record: LeadScoreRecord) -> None:
        _require_scope(scope, record.tenant_id)
        self._session.add(
            LeadScoreRow(
                id=record.id,
                tenant_id=record.tenant_id,
                lead_id=record.lead_id,
                total_score=record.total_score,
                classification=record.classification.value,
                is_qualified=record.is_qualified,
                distinct_buying_signals=record.distinct_buying_signals,
                breakdown=record.breakdown,
                ruleset_version=record.ruleset_version,
                scored_at=record.scored_at,
            )
        )


class SqlAlchemyEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scope: TenantScope, evidence_id: EvidenceId) -> Evidence | None:
        row = await self._session.get(EvidenceRow, evidence_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _evidence_from_row(row)

    async def list_for_lead(self, scope: TenantScope, lead_id: LeadId) -> list[Evidence]:
        stmt = select(EvidenceRow).where(
            EvidenceRow.tenant_id == scope.tenant_id,
            EvidenceRow.lead_id == lead_id,
        )
        result = await self._session.execute(stmt)
        return [_evidence_from_row(row) for row in result.scalars().all()]

    async def list_for_locator(self, scope: TenantScope, locator: str) -> list[Evidence]:
        stmt = select(EvidenceRow).where(
            EvidenceRow.tenant_id == scope.tenant_id,
            EvidenceRow.source_locator == locator,
        )
        result = await self._session.execute(stmt)
        return [_evidence_from_row(row) for row in result.scalars().all()]

    async def list_for_company(self, scope: TenantScope, company_id: CompanyId) -> list[Evidence]:
        stmt = select(EvidenceRow).where(
            EvidenceRow.tenant_id == scope.tenant_id,
            EvidenceRow.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return [_evidence_from_row(row) for row in result.scalars().all()]

    async def add(self, scope: TenantScope, evidence: Evidence) -> Evidence:
        _require_scope(scope, evidence.tenant_id)
        self._session.add(
            EvidenceRow(
                id=evidence.id,
                tenant_id=evidence.tenant_id,
                company_id=evidence.company_id,
                person_id=evidence.person_id,
                lead_id=evidence.lead_id,
                fact=evidence.fact,
                origin=evidence.origin.value,
                source_class=evidence.source_class.value if evidence.source_class else None,
                source_locator=evidence.source_locator,
                collected_at=evidence.collected_at,
                confidence=evidence.confidence.value,
                snippet=evidence.snippet,
                metadata_json=evidence.metadata,
            )
        )
        return evidence

    async def upsert(self, scope: TenantScope, evidence: Evidence) -> Evidence:
        _require_scope(scope, evidence.tenant_id)
        row = await self._session.get(EvidenceRow, evidence.id)
        if row is None:
            existing = await self.list_for_locator(scope, evidence.source_locator or "")
            kind = evidence.metadata.get("fact_kind")
            match = next(
                (item for item in existing if item.metadata.get("fact_kind") == kind),
                None,
            )
            if match is not None:
                row = await self._session.get(EvidenceRow, match.id)
                evidence.id = match.id
        if row is None:
            return await self.add(scope, evidence)
        if row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Evidence belongs to another tenant.")
        row.company_id = evidence.company_id
        row.person_id = evidence.person_id
        row.lead_id = evidence.lead_id
        row.fact = evidence.fact
        row.origin = evidence.origin.value
        row.source_class = evidence.source_class.value if evidence.source_class else None
        row.source_locator = evidence.source_locator
        row.collected_at = evidence.collected_at
        row.confidence = evidence.confidence.value
        row.snippet = evidence.snippet
        row.metadata_json = evidence.metadata
        return evidence


def _company_from_row(row: CompanyRow) -> Company:
    return Company(
        id=CompanyId(row.id),
        tenant_id=TenantId(row.tenant_id),
        name=row.name,
        normalized_name=row.normalized_name,
        website=row.website,
        industry=Industry(row.industry) if row.industry else None,
        geography=Geography(row.geography) if row.geography else None,
        employee_count=row.employee_count,
        headcount_growth_pct=row.headcount_growth_pct,
        company_type=CompanyType(row.company_type) if row.company_type else None,
        is_hiring=row.is_hiring,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _person_from_row(row: PersonRow) -> Person:
    return Person(
        id=PersonId(row.id),
        tenant_id=TenantId(row.tenant_id),
        company_id=CompanyId(row.company_id) if row.company_id else None,
        full_name=row.full_name,
        title=row.title,
        function=DecisionFunction(row.function) if row.function else None,
        seniority=Seniority(row.seniority) if row.seniority else None,
        location=row.location,
        years_in_role=row.years_in_role,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _lead_from_row(row: LeadRow) -> Lead:
    return Lead(
        id=LeadId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=row.workspace_id,  # type: ignore[arg-type]
        company_id=CompanyId(row.company_id),
        person_id=PersonId(row.person_id) if row.person_id else None,
        status=LeadStatus(row.status),
        score=row.score,
        classification=LeadClassification(row.classification),
        is_qualified=row.is_qualified,
        search_profile_id=row.search_profile_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _company_source_from_row(row: CompanySourceRow) -> CompanySource:
    return CompanySource(
        id=row.id,
        tenant_id=TenantId(row.tenant_id),
        company_id=CompanyId(row.company_id),
        source_class=SourceClass(row.source_class),
        locator=row.locator,
        raw_reference=row.raw_reference,
        collected_at=row.collected_at,
    )


def _evidence_from_row(row: EvidenceRow) -> Evidence:
    return Evidence(
        id=EvidenceId(row.id),
        tenant_id=TenantId(row.tenant_id),
        fact=row.fact,
        origin=EvidenceOrigin(row.origin),
        source_class=SourceClass(row.source_class) if row.source_class else None,
        source_locator=row.source_locator,
        collected_at=row.collected_at,
        confidence=Confidence(row.confidence),
        snippet=row.snippet,
        company_id=CompanyId(row.company_id) if row.company_id else None,
        person_id=PersonId(row.person_id) if row.person_id else None,
        lead_id=LeadId(row.lead_id) if row.lead_id else None,
        metadata=row.metadata_json,
    )


class SqlAlchemySignalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scope: TenantScope, signal_id: SignalId) -> Signal | None:
        row = await self._session.get(SignalRow, signal_id)
        if row is None:
            return None
        _require_scope(scope, row.tenant_id)
        return _signal_from_row(row)

    async def list_for_company(self, scope: TenantScope, company_id: CompanyId) -> list[Signal]:
        stmt = select(SignalRow).where(
            SignalRow.tenant_id == scope.tenant_id,
            SignalRow.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return [_signal_from_row(row) for row in result.scalars().all()]

    async def get_by_company_and_type(
        self, scope: TenantScope, company_id: CompanyId, signal_type: SignalType
    ) -> Signal | None:
        stmt = select(SignalRow).where(
            SignalRow.tenant_id == scope.tenant_id,
            SignalRow.company_id == company_id,
            SignalRow.signal_type == signal_type.value,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _signal_from_row(row) if row else None

    async def upsert(self, scope: TenantScope, signal: Signal) -> Signal:
        _require_scope(scope, signal.tenant_id)
        row = await self._session.get(SignalRow, signal.id)
        if row is None and signal.company_id is not None:
            existing = await self.get_by_company_and_type(
                scope, signal.company_id, signal.signal_type
            )
            if existing is not None:
                row = await self._session.get(SignalRow, existing.id)
                signal.id = existing.id
        if row is None:
            self._session.add(
                SignalRow(
                    id=signal.id,
                    tenant_id=signal.tenant_id,
                    company_id=signal.company_id,
                    person_id=signal.person_id,
                    lead_id=signal.lead_id,
                    signal_type=signal.signal_type.value,
                    weight=signal.weight,
                    detected_at=signal.detected_at,
                    evidence_id=signal.evidence_id,
                    reason=signal.reason,
                )
            )
            return signal
        if row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Signal belongs to another tenant.")
        row.person_id = signal.person_id
        row.lead_id = signal.lead_id
        row.weight = signal.weight
        row.detected_at = signal.detected_at
        row.evidence_id = signal.evidence_id
        row.reason = signal.reason
        return signal

    async def delete(self, scope: TenantScope, signal_id: SignalId) -> None:
        row = await self._session.get(SignalRow, signal_id)
        if row is None:
            return
        _require_scope(scope, row.tenant_id)
        await self._session.delete(row)


def _signal_from_row(row: SignalRow) -> Signal:
    return Signal(
        id=SignalId(row.id),
        tenant_id=TenantId(row.tenant_id),
        company_id=CompanyId(row.company_id) if row.company_id else None,
        signal_type=SignalType(row.signal_type),
        weight=row.weight,
        detected_at=row.detected_at,
        evidence_id=EvidenceId(row.evidence_id),
        person_id=PersonId(row.person_id) if row.person_id else None,
        lead_id=LeadId(row.lead_id) if row.lead_id else None,
        reason=row.reason,
    )


class SqlAlchemyDiscoveryCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, scope: TenantScope, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        _require_scope(scope, candidate.tenant_id)
        row = await self._session.get(DiscoveryCandidateRow, candidate.id)
        if row is None:
            existing = await self.get_by_locator(
                scope, candidate.discovery_job_id, candidate.source_locator
            )
            if existing is not None:
                row = await self._session.get(DiscoveryCandidateRow, existing.id)
                candidate.id = existing.id
        if row is None:
            self._session.add(
                DiscoveryCandidateRow(
                    id=candidate.id,
                    tenant_id=candidate.tenant_id,
                    discovery_job_id=candidate.discovery_job_id,
                    name=candidate.name,
                    domain=candidate.domain,
                    website_url=candidate.website_url,
                    normalized_website=candidate.normalized_website,
                    provider_key=candidate.provider_key,
                    source_locator=candidate.source_locator,
                    discovered_at=candidate.discovered_at,
                    confidence=candidate.confidence,
                    provider_rank=candidate.provider_rank,
                    field_checks_json=candidate.field_checks,
                    evidence_id=candidate.evidence_id,
                    company_id=candidate.company_id,
                    fetch_job_id=candidate.fetch_job_id,
                    research_job_id=candidate.research_job_id,
                    lead_id=candidate.lead_id,
                    source_evidence_ids=candidate.source_evidence_ids,
                    ingestion_status=candidate.ingestion_status.value,
                    request_snapshot=candidate.request_snapshot,
                    created_at=candidate.created_at,
                    updated_at=candidate.updated_at,
                )
            )
            return candidate
        if row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Discovery candidate belongs to another tenant.")
        row.name = candidate.name
        row.domain = candidate.domain
        row.website_url = candidate.website_url
        row.normalized_website = candidate.normalized_website
        row.provider_key = candidate.provider_key
        row.source_locator = candidate.source_locator
        row.discovered_at = candidate.discovered_at
        row.confidence = candidate.confidence
        row.provider_rank = candidate.provider_rank
        row.field_checks_json = candidate.field_checks
        row.evidence_id = candidate.evidence_id
        row.company_id = candidate.company_id
        row.fetch_job_id = candidate.fetch_job_id
        row.research_job_id = candidate.research_job_id
        row.lead_id = candidate.lead_id
        row.source_evidence_ids = candidate.source_evidence_ids
        row.ingestion_status = candidate.ingestion_status.value
        row.request_snapshot = candidate.request_snapshot
        row.updated_at = candidate.updated_at
        return candidate

    async def list_for_job(self, scope: TenantScope, job_id: JobId) -> list[DiscoveryCandidate]:
        stmt = select(DiscoveryCandidateRow).where(
            DiscoveryCandidateRow.tenant_id == scope.tenant_id,
            DiscoveryCandidateRow.discovery_job_id == job_id,
        )
        result = await self._session.execute(stmt)
        return [_discovery_candidate_from_row(row) for row in result.scalars().all()]

    async def get_by_locator(
        self, scope: TenantScope, job_id: JobId, source_locator: str
    ) -> DiscoveryCandidate | None:
        stmt = select(DiscoveryCandidateRow).where(
            DiscoveryCandidateRow.tenant_id == scope.tenant_id,
            DiscoveryCandidateRow.discovery_job_id == job_id,
            DiscoveryCandidateRow.source_locator == source_locator,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _discovery_candidate_from_row(row) if row else None

    async def get_by_id(self, scope: TenantScope, candidate_id: UUID) -> DiscoveryCandidate | None:
        row = await self._session.get(DiscoveryCandidateRow, candidate_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _discovery_candidate_from_row(row)

    async def find_by_id(self, candidate_id: UUID) -> DiscoveryCandidate | None:
        row = await self._session.get(DiscoveryCandidateRow, candidate_id)
        return _discovery_candidate_from_row(row) if row else None

    async def get_by_fetch_job_id(
        self, scope: TenantScope, fetch_job_id: JobId
    ) -> DiscoveryCandidate | None:
        stmt = select(DiscoveryCandidateRow).where(
            DiscoveryCandidateRow.tenant_id == scope.tenant_id,
            DiscoveryCandidateRow.fetch_job_id == fetch_job_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _discovery_candidate_from_row(row) if row else None

    async def list_for_tenant(
        self,
        scope: TenantScope,
        *,
        ingestion_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiscoveryCandidate]:
        stmt = (
            select(DiscoveryCandidateRow)
            .where(DiscoveryCandidateRow.tenant_id == scope.tenant_id)
            .order_by(DiscoveryCandidateRow.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if ingestion_status is not None:
            stmt = stmt.where(DiscoveryCandidateRow.ingestion_status == ingestion_status)
        result = await self._session.execute(stmt)
        return [_discovery_candidate_from_row(row) for row in result.scalars().all()]


class SqlAlchemyCompanyResearchCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, scope: TenantScope, case: CompanyResearchCase) -> CompanyResearchCase:
        _require_scope(scope, case.tenant_id)
        self._session.add(
            CompanyResearchCaseRow(
                id=case.id,
                tenant_id=case.tenant_id,
                company_id=case.company_id,
                status=case.status.value,
                job_id=case.job_id,
                requested_at=case.requested_at,
                started_at=case.started_at,
                completed_at=case.completed_at,
                failed_at=case.failed_at,
                pages_requested=case.pages_requested,
                pages_fetched=case.pages_fetched,
                pages_failed=case.pages_failed,
                research_version=case.research_version,
                error_code=case.error_code.value if case.error_code else None,
                error_message_safe=case.error_message_safe,
                created_at=case.created_at,
                updated_at=case.updated_at,
            )
        )
        return case

    async def update(self, scope: TenantScope, case: CompanyResearchCase) -> CompanyResearchCase:
        _require_scope(scope, case.tenant_id)
        row = await self._session.get(CompanyResearchCaseRow, case.id)
        if row is None or row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Research case not found in tenant scope.")
        row.status = case.status.value
        row.job_id = case.job_id
        row.started_at = case.started_at
        row.completed_at = case.completed_at
        row.failed_at = case.failed_at
        row.pages_requested = case.pages_requested
        row.pages_fetched = case.pages_fetched
        row.pages_failed = case.pages_failed
        row.error_code = case.error_code.value if case.error_code else None
        row.error_message_safe = case.error_message_safe
        row.updated_at = case.updated_at
        return case

    async def get(self, scope: TenantScope, case_id: UUID) -> CompanyResearchCase | None:
        row = await self._session.get(CompanyResearchCaseRow, case_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _company_research_case_from_row(row)

    async def get_latest_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> CompanyResearchCase | None:
        stmt = (
            select(CompanyResearchCaseRow)
            .where(
                CompanyResearchCaseRow.tenant_id == scope.tenant_id,
                CompanyResearchCaseRow.company_id == company_id,
            )
            .order_by(CompanyResearchCaseRow.requested_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _company_research_case_from_row(row) if row else None


class SqlAlchemyResearchPageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, scope: TenantScope, page: ResearchPage) -> ResearchPage:
        _require_scope(scope, page.tenant_id)
        self._session.add(
            ResearchPageRow(
                id=page.id,
                tenant_id=page.tenant_id,
                research_case_id=page.research_case_id,
                company_id=page.company_id,
                url=page.url,
                normalized_url=page.normalized_url,
                page_type=page.page_type.value,
                title=page.title,
                http_status=page.http_status,
                content_type=page.content_type,
                content_hash=page.content_hash,
                normalized_text=page.normalized_text,
                fetched_at=page.fetched_at,
                fetch_duration_ms=page.fetch_duration_ms,
                fetch_status=page.fetch_status.value,
                failure_class=page.failure_class,
                evidence_id=page.evidence_id,
                created_at=page.created_at,
                updated_at=page.updated_at,
            )
        )
        return page

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[ResearchPage]:
        stmt = select(ResearchPageRow).where(
            ResearchPageRow.tenant_id == scope.tenant_id,
            ResearchPageRow.research_case_id == case_id,
        )
        result = await self._session.execute(stmt)
        return [_research_page_from_row(row) for row in result.scalars().all()]


def _company_research_case_from_row(row: CompanyResearchCaseRow) -> CompanyResearchCase:
    error_code = ResearchErrorCode(row.error_code) if row.error_code else None
    return CompanyResearchCase(
        id=row.id,
        tenant_id=TenantId(row.tenant_id),
        company_id=CompanyId(row.company_id),
        status=CompanyResearchStatus(row.status),
        job_id=JobId(row.job_id) if row.job_id else None,
        requested_at=row.requested_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failed_at=row.failed_at,
        pages_requested=row.pages_requested,
        pages_fetched=row.pages_fetched,
        pages_failed=row.pages_failed,
        research_version=row.research_version,
        error_code=error_code,
        error_message_safe=row.error_message_safe,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _research_page_from_row(row: ResearchPageRow) -> ResearchPage:
    return ResearchPage(
        id=row.id,
        tenant_id=TenantId(row.tenant_id),
        research_case_id=row.research_case_id,
        company_id=CompanyId(row.company_id),
        url=row.url,
        normalized_url=row.normalized_url,
        page_type=ResearchPageType(row.page_type),
        title=row.title,
        http_status=row.http_status,
        content_type=row.content_type,
        content_hash=row.content_hash,
        normalized_text=row.normalized_text,
        fetched_at=row.fetched_at,
        fetch_duration_ms=row.fetch_duration_ms,
        fetch_status=ResearchPageFetchStatus(row.fetch_status),
        failure_class=row.failure_class,
        evidence_id=EvidenceId(row.evidence_id) if row.evidence_id else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyCompanyFactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, scope: TenantScope, fact: CompanyFact) -> tuple[CompanyFact, bool]:
        _require_scope(scope, fact.tenant_id)
        stmt = select(CompanyFactRow).where(
            CompanyFactRow.tenant_id == scope.tenant_id,
            CompanyFactRow.research_case_id == fact.research_case_id,
            CompanyFactRow.dedupe_key == fact.dedupe_key,
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            self._session.add(
                CompanyFactRow(
                    id=fact.id,
                    tenant_id=fact.tenant_id,
                    company_id=fact.company_id,
                    research_case_id=fact.research_case_id,
                    category=fact.category.value,
                    subject=fact.subject,
                    value=fact.value,
                    evidence_ids_json=[str(item) for item in fact.evidence_ids],
                    origin=fact.origin.value,
                    confidence=fact.confidence.value,
                    fact_tier=fact.fact_tier.value,
                    extraction_method=fact.extraction_method,
                    extraction_version=fact.extraction_version,
                    status=fact.status.value,
                    dedupe_key=fact.dedupe_key,
                    extracted_at=fact.extracted_at,
                    created_at=fact.created_at,
                    updated_at=fact.updated_at,
                )
            )
            return fact, True

        existing.category = fact.category.value
        existing.subject = fact.subject
        existing.value = fact.value
        existing.evidence_ids_json = [str(item) for item in fact.evidence_ids]
        existing.origin = fact.origin.value
        existing.confidence = fact.confidence.value
        existing.fact_tier = fact.fact_tier.value
        existing.extraction_method = fact.extraction_method
        existing.extraction_version = fact.extraction_version
        existing.status = fact.status.value
        existing.extracted_at = fact.extracted_at
        existing.updated_at = fact.updated_at
        return _company_fact_from_row(existing), False

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[CompanyFact]:
        stmt = select(CompanyFactRow).where(
            CompanyFactRow.tenant_id == scope.tenant_id,
            CompanyFactRow.research_case_id == case_id,
            CompanyFactRow.status == CompanyFactStatus.ACTIVE.value,
        )
        result = await self._session.execute(stmt)
        return [_company_fact_from_row(row) for row in result.scalars().all()]

    async def list_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> list[CompanyFact]:
        stmt = select(CompanyFactRow).where(
            CompanyFactRow.tenant_id == scope.tenant_id,
            CompanyFactRow.company_id == company_id,
            CompanyFactRow.status == CompanyFactStatus.ACTIVE.value,
        )
        result = await self._session.execute(stmt)
        return [_company_fact_from_row(row) for row in result.scalars().all()]


def _company_fact_from_row(row: CompanyFactRow) -> CompanyFact:
    return CompanyFact(
        id=CompanyFactId(row.id),
        tenant_id=TenantId(row.tenant_id),
        company_id=CompanyId(row.company_id),
        research_case_id=row.research_case_id,
        category=CompanyFactCategory(row.category),
        subject=row.subject,
        value=row.value,
        evidence_ids=[EvidenceId(UUID(item)) for item in row.evidence_ids_json],
        origin=EvidenceOrigin(row.origin),
        confidence=Confidence(row.confidence),
        fact_tier=CompanyFactTier(row.fact_tier),
        extraction_method=row.extraction_method,
        extraction_version=row.extraction_version,
        status=CompanyFactStatus(row.status),
        dedupe_key=row.dedupe_key,
        extracted_at=row.extracted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyImportBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, scope: TenantScope, batch: ImportBatch) -> ImportBatch:
        _require_scope(scope, batch.tenant_id)
        self._session.add(
            ImportBatchRow(
                id=batch.id,
                tenant_id=batch.tenant_id,
                source_filename=batch.source_filename,
                provider=batch.provider,
                status=batch.status.value,
                column_mapping_json=batch.column_mapping,
                detected_headers_json=batch.detected_headers,
                total_rows=batch.total_rows,
                imported_rows=batch.imported_rows,
                skipped_rows=batch.skipped_rows,
                error_rows=batch.error_rows,
                duplicate_rows=batch.duplicate_rows,
                errors_json=batch.errors,
                dry_run=batch.dry_run,
                content_hash=batch.content_hash,
                stored_content=batch.stored_content,
                job_id=batch.job_id,
                created_at=batch.created_at,
                updated_at=batch.updated_at,
                completed_at=batch.completed_at,
            )
        )
        return batch

    async def update(self, scope: TenantScope, batch: ImportBatch) -> ImportBatch:
        _require_scope(scope, batch.tenant_id)
        row = await self._session.get(ImportBatchRow, batch.id)
        if row is None or row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Import batch not found in tenant scope.")
        row.status = batch.status.value
        row.imported_rows = batch.imported_rows
        row.skipped_rows = batch.skipped_rows
        row.error_rows = batch.error_rows
        row.duplicate_rows = batch.duplicate_rows
        row.errors_json = batch.errors
        row.job_id = batch.job_id
        row.updated_at = batch.updated_at
        row.completed_at = batch.completed_at
        return batch

    async def get(self, scope: TenantScope, batch_id: ImportBatchId) -> ImportBatch | None:
        row = await self._session.get(ImportBatchRow, batch_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _import_batch_from_row(row)


class SqlAlchemyImportedProspectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, scope: TenantScope, prospect: ImportedProspect) -> ImportedProspect:
        _require_scope(scope, prospect.tenant_id)
        self._session.add(
            ImportedProspectRow(
                id=prospect.id,
                tenant_id=prospect.tenant_id,
                import_batch_id=prospect.import_batch_id,
                source_row_number=prospect.source_row_number,
                status=prospect.status.value,
                resolution_status=prospect.resolution_status.value,
                company_id=prospect.company_id,
                person_id=prospect.person_id,
                duplicate_of_id=prospect.duplicate_of_id,
                duplicate_key=prospect.duplicate_key,
                error_message=prospect.error_message,
                raw_data_json=prospect.raw_data,
                normalized_data_json=prospect.normalized_data,
                provider=prospect.provider,
                created_at=prospect.created_at,
                updated_at=prospect.updated_at,
            )
        )
        return prospect

    async def update(self, scope: TenantScope, prospect: ImportedProspect) -> ImportedProspect:
        _require_scope(scope, prospect.tenant_id)
        row = await self._session.get(ImportedProspectRow, prospect.id)
        if row is None or row.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Imported prospect not found in tenant scope.")
        row.status = prospect.status.value
        row.resolution_status = prospect.resolution_status.value
        row.company_id = prospect.company_id
        row.person_id = prospect.person_id
        row.error_message = prospect.error_message
        row.updated_at = prospect.updated_at
        return prospect

    async def get(
        self, scope: TenantScope, prospect_id: ImportedProspectId
    ) -> ImportedProspect | None:
        row = await self._session.get(ImportedProspectRow, prospect_id)
        if row is None or row.tenant_id != scope.tenant_id:
            return None
        return _imported_prospect_from_row(row)

    async def find_by_duplicate_key(
        self, scope: TenantScope, duplicate_key: str | None
    ) -> ImportedProspect | None:
        if not duplicate_key:
            return None
        stmt = select(ImportedProspectRow).where(
            ImportedProspectRow.tenant_id == scope.tenant_id,
            ImportedProspectRow.duplicate_key == duplicate_key,
            ImportedProspectRow.status == ImportedProspectStatus.IMPORTED.value,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _imported_prospect_from_row(row) if row else None

    async def list_for_tenant(
        self,
        scope: TenantScope,
        *,
        batch_id: ImportBatchId | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ImportedProspect]:
        stmt = (
            select(ImportedProspectRow)
            .where(ImportedProspectRow.tenant_id == scope.tenant_id)
            .order_by(ImportedProspectRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if batch_id is not None:
            stmt = stmt.where(ImportedProspectRow.import_batch_id == batch_id)
        result = await self._session.execute(stmt)
        return [_imported_prospect_from_row(row) for row in result.scalars().all()]

    async def list_for_batch(
        self, scope: TenantScope, batch_id: ImportBatchId
    ) -> list[ImportedProspect]:
        return await self.list_for_tenant(scope, batch_id=batch_id, limit=10_000, offset=0)


def _import_batch_from_row(row: ImportBatchRow) -> ImportBatch:
    return ImportBatch(
        id=ImportBatchId(row.id),
        tenant_id=TenantId(row.tenant_id),
        source_filename=row.source_filename,
        provider=row.provider,
        status=ImportBatchStatus(row.status),
        column_mapping=dict(row.column_mapping_json),
        detected_headers=list(row.detected_headers_json),
        total_rows=row.total_rows,
        imported_rows=row.imported_rows,
        skipped_rows=row.skipped_rows,
        error_rows=row.error_rows,
        duplicate_rows=row.duplicate_rows,
        errors=list(row.errors_json or []),
        dry_run=row.dry_run,
        job_id=row.job_id,
        content_hash=row.content_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        stored_content=row.stored_content,
    )


def _imported_prospect_from_row(row: ImportedProspectRow) -> ImportedProspect:
    return ImportedProspect(
        id=ImportedProspectId(row.id),
        tenant_id=TenantId(row.tenant_id),
        import_batch_id=ImportBatchId(row.import_batch_id),
        source_row_number=row.source_row_number,
        status=ImportedProspectStatus(row.status),
        resolution_status=ResolutionStatus(row.resolution_status),
        company_id=CompanyId(row.company_id) if row.company_id else None,
        person_id=PersonId(row.person_id) if row.person_id else None,
        duplicate_of_id=ImportedProspectId(row.duplicate_of_id) if row.duplicate_of_id else None,
        duplicate_key=row.duplicate_key,
        error_message=row.error_message,
        raw_data=dict(row.raw_data_json),
        normalized_data=dict(row.normalized_data_json),
        provider=row.provider,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _discovery_candidate_from_row(row: DiscoveryCandidateRow) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        id=row.id,
        tenant_id=TenantId(row.tenant_id),
        discovery_job_id=JobId(row.discovery_job_id),
        name=row.name,
        domain=row.domain,
        website_url=row.website_url,
        normalized_website=row.normalized_website,
        provider_key=row.provider_key,
        source_locator=row.source_locator,
        discovered_at=row.discovered_at,
        confidence=row.confidence,
        provider_rank=row.provider_rank,
        field_checks=row.field_checks_json,
        evidence_id=EvidenceId(row.evidence_id) if row.evidence_id else None,
        company_id=CompanyId(row.company_id) if row.company_id else None,
        fetch_job_id=JobId(row.fetch_job_id) if row.fetch_job_id else None,
        research_job_id=JobId(row.research_job_id) if row.research_job_id else None,
        lead_id=LeadId(row.lead_id) if row.lead_id else None,
        source_evidence_ids=list(row.source_evidence_ids or []),
        ingestion_status=DiscoveryIngestionStatus(row.ingestion_status),
        request_snapshot=row.request_snapshot,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
