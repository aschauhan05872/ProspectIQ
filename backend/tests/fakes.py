from __future__ import annotations

from uuid import UUID

from prospectiq.domain.common import (
    CompanyId,
    EvidenceId,
    ImportBatchId,
    ImportedProspectId,
    JobId,
    PersonId,
    SignalId,
    TenantScope,
)
from prospectiq.domain.company import Company, CompanySource
from prospectiq.domain.company_facts import CompanyFact, CompanyFactStatus
from prospectiq.domain.company_research import CompanyResearchCase, ResearchPage
from prospectiq.domain.discovery import DiscoveryCandidate
from prospectiq.domain.evidence import Evidence
from prospectiq.domain.lead import Lead, LeadScoreRecord
from prospectiq.domain.person import Person
from prospectiq.domain.prospect_import import ImportBatch, ImportedProspect, ImportedProspectStatus
from prospectiq.domain.signal import Signal, SignalType
from prospectiq.infrastructure.repositories import TenantMismatchError, _require_scope


class InMemoryCompanyRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], Company] = {}

    async def get(self, scope: TenantScope, company_id: CompanyId) -> Company | None:
        company = self.items.get((scope.tenant_id, company_id))
        return company

    async def get_by_normalized_name(
        self, scope: TenantScope, normalized_name: str
    ) -> Company | None:
        for (tenant_id, _), company in self.items.items():
            if tenant_id == scope.tenant_id and company.normalized_name == normalized_name:
                return company
        return None

    async def upsert(self, scope: TenantScope, company: Company) -> Company:
        _require_scope(scope, company.tenant_id)
        self.items[(scope.tenant_id, company.id)] = company
        return company


class InMemoryCompanySourceRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, str], CompanySource] = {}

    async def get_by_locator(self, scope: TenantScope, locator: str) -> CompanySource | None:
        return self.items.get((scope.tenant_id, locator))

    async def upsert(self, scope: TenantScope, source: CompanySource) -> CompanySource:
        _require_scope(scope, source.tenant_id)
        existing = self.items.get((scope.tenant_id, source.locator))
        if existing is not None and existing.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Company source belongs to another tenant.")
        self.items[(scope.tenant_id, source.locator)] = source
        return source


class InMemoryEvidenceRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], Evidence] = {}

    async def get(self, scope: TenantScope, evidence_id: EvidenceId) -> Evidence | None:
        return self.items.get((scope.tenant_id, evidence_id))

    async def list_for_lead(self, scope: TenantScope, lead_id: object) -> list[Evidence]:
        return [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.lead_id == lead_id
        ]

    async def list_for_locator(self, scope: TenantScope, locator: str) -> list[Evidence]:
        return [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.source_locator == locator
        ]

    async def list_for_company(self, scope: TenantScope, company_id: CompanyId) -> list[Evidence]:
        return [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.company_id == company_id
        ]

    async def add(self, scope: TenantScope, evidence: Evidence) -> Evidence:
        _require_scope(scope, evidence.tenant_id)
        self.items[(scope.tenant_id, evidence.id)] = evidence
        return evidence

    async def upsert(self, scope: TenantScope, evidence: Evidence) -> Evidence:
        _require_scope(scope, evidence.tenant_id)
        existing = await self.list_for_locator(scope, evidence.source_locator or "")
        kind = evidence.metadata.get("fact_kind")
        match = next((item for item in existing if item.metadata.get("fact_kind") == kind), None)
        if match is not None:
            evidence.id = match.id
        self.items[(scope.tenant_id, evidence.id)] = evidence
        return evidence


class InMemoryLeadRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], Lead] = {}
        self.scores: list[LeadScoreRecord] = []

    async def get(self, scope: TenantScope, lead_id: object) -> Lead | None:
        return self.items.get((scope.tenant_id, lead_id))  # type: ignore[arg-type]

    async def list_for_workspace(
        self,
        scope: TenantScope,
        *,
        limit: int = 50,
        offset: int = 0,
        is_qualified: bool | None = None,
        classification: str | None = None,
    ) -> list[Lead]:
        rows = [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id
            and (scope.workspace_id is None or item.workspace_id == scope.workspace_id)
            and (is_qualified is None or item.is_qualified is is_qualified)
            and (classification is None or item.classification.value == classification)
        ]
        return rows[offset : offset + limit]

    async def get_by_company(self, scope: TenantScope, company_id: CompanyId) -> Lead | None:
        matches = [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id
            and item.company_id == company_id
            and item.person_id is None
            and (scope.workspace_id is None or item.workspace_id == scope.workspace_id)
        ]
        return matches[0] if matches else None

    async def upsert(self, scope: TenantScope, lead: Lead) -> Lead:
        _require_scope(scope, lead.tenant_id)
        self.items[(scope.tenant_id, lead.id)] = lead
        return lead

    async def save_score(self, scope: TenantScope, record: LeadScoreRecord) -> None:
        _require_scope(scope, record.tenant_id)
        self.scores.append(record)


class InMemorySignalRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], Signal] = {}

    async def list_for_company(self, scope: TenantScope, company_id: CompanyId) -> list[Signal]:
        return [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.company_id == company_id
        ]

    async def get_by_company_and_type(
        self, scope: TenantScope, company_id: CompanyId, signal_type: SignalType
    ) -> Signal | None:
        for (tenant_id, _), item in self.items.items():
            if (
                tenant_id == scope.tenant_id
                and item.company_id == company_id
                and item.signal_type is signal_type
            ):
                return item
        return None

    async def upsert(self, scope: TenantScope, signal: Signal) -> Signal:
        _require_scope(scope, signal.tenant_id)
        if signal.company_id is not None:
            existing = await self.get_by_company_and_type(
                scope, signal.company_id, signal.signal_type
            )
            if existing is not None:
                signal.id = existing.id
        self.items[(scope.tenant_id, signal.id)] = signal
        return signal

    async def delete(self, scope: TenantScope, signal_id: SignalId) -> None:
        signal = self.items.get((scope.tenant_id, signal_id))
        if signal is None:
            return
        _require_scope(scope, signal.tenant_id)
        self.items.pop((scope.tenant_id, signal_id), None)


class InMemoryDiscoveryCandidateRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], DiscoveryCandidate] = {}

    async def upsert(self, scope: TenantScope, candidate: DiscoveryCandidate) -> DiscoveryCandidate:
        _require_scope(scope, candidate.tenant_id)
        existing = await self.get_by_locator(
            scope, candidate.discovery_job_id, candidate.source_locator
        )
        if existing is not None:
            candidate.id = existing.id
            candidate.created_at = existing.created_at
        self.items[(scope.tenant_id, candidate.id)] = candidate
        return candidate

    async def list_for_job(self, scope: TenantScope, job_id: JobId) -> list[DiscoveryCandidate]:
        return [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.discovery_job_id == job_id
        ]

    async def get_by_locator(
        self, scope: TenantScope, job_id: JobId, source_locator: str
    ) -> DiscoveryCandidate | None:
        for (tenant_id, _), item in self.items.items():
            if (
                tenant_id == scope.tenant_id
                and item.discovery_job_id == job_id
                and item.source_locator == source_locator
            ):
                return item
        return None

    async def get_by_id(self, scope: TenantScope, candidate_id: UUID) -> DiscoveryCandidate | None:
        item = self.items.get((scope.tenant_id, candidate_id))
        return item

    async def find_by_id(self, candidate_id: UUID) -> DiscoveryCandidate | None:
        for (_, cid), item in self.items.items():
            if cid == candidate_id:
                return item
        return None

    async def get_by_fetch_job_id(
        self, scope: TenantScope, fetch_job_id: JobId
    ) -> DiscoveryCandidate | None:
        for (tenant_id, _), item in self.items.items():
            if tenant_id == scope.tenant_id and item.fetch_job_id == fetch_job_id:
                return item
        return None

    async def list_for_tenant(
        self,
        scope: TenantScope,
        *,
        ingestion_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiscoveryCandidate]:
        rows = [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id
            and (ingestion_status is None or item.ingestion_status.value == ingestion_status)
        ]
        return rows[offset : offset + limit]


class InMemoryPersonRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], Person] = {}

    async def get(self, scope: TenantScope, person_id: PersonId) -> Person | None:
        return self.items.get((scope.tenant_id, person_id))

    async def upsert(self, scope: TenantScope, person: Person) -> Person:
        _require_scope(scope, person.tenant_id)
        self.items[(scope.tenant_id, person.id)] = person
        return person


class InMemoryCompanyResearchCaseRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], CompanyResearchCase] = {}

    async def create(self, scope: TenantScope, case: CompanyResearchCase) -> CompanyResearchCase:
        _require_scope(scope, case.tenant_id)
        self.items[(scope.tenant_id, case.id)] = case
        return case

    async def update(self, scope: TenantScope, case: CompanyResearchCase) -> CompanyResearchCase:
        _require_scope(scope, case.tenant_id)
        self.items[(scope.tenant_id, case.id)] = case
        return case

    async def get(self, scope: TenantScope, case_id: UUID) -> CompanyResearchCase | None:
        return self.items.get((scope.tenant_id, case_id))

    async def get_latest_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> CompanyResearchCase | None:
        matches = [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.company_id == company_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.requested_at)


class InMemoryResearchPageRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], ResearchPage] = {}

    async def create(self, scope: TenantScope, page: ResearchPage) -> ResearchPage:
        _require_scope(scope, page.tenant_id)
        self.items[(scope.tenant_id, page.id)] = page
        return page

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[ResearchPage]:
        return [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id and item.research_case_id == case_id
        ]


class InMemoryCompanyFactRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID, str], CompanyFact] = {}

    async def upsert(self, scope: TenantScope, fact: CompanyFact) -> tuple[CompanyFact, bool]:
        _require_scope(scope, fact.tenant_id)
        key = (scope.tenant_id, fact.research_case_id, fact.dedupe_key)
        existing = self.items.get(key)
        if existing is None:
            self.items[key] = fact
            return fact, True
        existing.category = fact.category
        existing.subject = fact.subject
        existing.value = fact.value
        existing.evidence_ids = fact.evidence_ids
        existing.origin = fact.origin
        existing.confidence = fact.confidence
        existing.extraction_method = fact.extraction_method
        existing.extraction_version = fact.extraction_version
        existing.status = fact.status
        existing.extracted_at = fact.extracted_at
        existing.updated_at = fact.updated_at
        return existing, False

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[CompanyFact]:
        return [
            item
            for (tenant_id, research_case_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id
            and research_case_id == case_id
            and item.status is CompanyFactStatus.ACTIVE
        ]

    async def list_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> list[CompanyFact]:
        return [
            item
            for (tenant_id, _, _), item in self.items.items()
            if tenant_id == scope.tenant_id
            and item.company_id == company_id
            and item.status is CompanyFactStatus.ACTIVE
        ]


class InMemoryImportBatchRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], ImportBatch] = {}

    async def create(self, scope: TenantScope, batch: ImportBatch) -> ImportBatch:
        _require_scope(scope, batch.tenant_id)
        self.items[(scope.tenant_id, batch.id)] = batch
        return batch

    async def update(self, scope: TenantScope, batch: ImportBatch) -> ImportBatch:
        _require_scope(scope, batch.tenant_id)
        self.items[(scope.tenant_id, batch.id)] = batch
        return batch

    async def get(self, scope: TenantScope, batch_id: ImportBatchId) -> ImportBatch | None:
        return self.items.get((scope.tenant_id, batch_id))


class InMemoryImportedProspectRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], ImportedProspect] = {}

    async def create(self, scope: TenantScope, prospect: ImportedProspect) -> ImportedProspect:
        _require_scope(scope, prospect.tenant_id)
        self.items[(scope.tenant_id, prospect.id)] = prospect
        return prospect

    async def update(self, scope: TenantScope, prospect: ImportedProspect) -> ImportedProspect:
        _require_scope(scope, prospect.tenant_id)
        self.items[(scope.tenant_id, prospect.id)] = prospect
        return prospect

    async def get(
        self, scope: TenantScope, prospect_id: ImportedProspectId
    ) -> ImportedProspect | None:
        return self.items.get((scope.tenant_id, prospect_id))

    async def find_by_duplicate_key(
        self, scope: TenantScope, duplicate_key: str | None
    ) -> ImportedProspect | None:
        if not duplicate_key:
            return None
        for (tenant_id, _), item in self.items.items():
            if (
                tenant_id == scope.tenant_id
                and item.duplicate_key == duplicate_key
                and item.status is ImportedProspectStatus.IMPORTED
            ):
                return item
        return None

    async def list_for_tenant(
        self,
        scope: TenantScope,
        *,
        batch_id: ImportBatchId | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ImportedProspect]:
        rows = [
            item
            for (tenant_id, _), item in self.items.items()
            if tenant_id == scope.tenant_id
            and (batch_id is None or item.import_batch_id == batch_id)
        ]
        return rows[offset : offset + limit]

    async def list_for_batch(
        self, scope: TenantScope, batch_id: ImportBatchId
    ) -> list[ImportedProspect]:
        return await self.list_for_tenant(scope, batch_id=batch_id, limit=10_000, offset=0)
