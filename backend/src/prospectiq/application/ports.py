"""Ports (interfaces) so domain/application code does not depend on vendors."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from prospectiq.domain.common import (
    CompanyId,
    EvidenceId,
    ImportBatchId,
    ImportedProspectId,
    JobId,
    LeadId,
    PersonId,
    SignalId,
    TenantScope,
)
from prospectiq.domain.company import Company, CompanySource
from prospectiq.domain.company_facts import CompanyFact, EvidencePageContext, ExtractedCompanyFact
from prospectiq.domain.company_research import CompanyResearchCase, ResearchPage
from prospectiq.domain.discovery import (
    CompanyCandidate,
    DiscoveryCandidate,
    DiscoveryRequest,
    ProviderDiscoveryHit,
    SearchProfile,
)
from prospectiq.domain.evidence import Evidence
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.lead import Lead, LeadScoreRecord
from prospectiq.domain.person import Person
from prospectiq.domain.prospect_import import ImportBatch, ImportedProspect
from prospectiq.domain.signal import Signal, SignalType
from prospectiq.domain.source_registry import SourceClass


class CompanyRepository(Protocol):
    async def get(self, scope: TenantScope, company_id: CompanyId) -> Company | None: ...

    async def get_by_normalized_name(
        self, scope: TenantScope, normalized_name: str
    ) -> Company | None: ...

    async def upsert(self, scope: TenantScope, company: Company) -> Company: ...


class CompanySourceRepository(Protocol):
    async def get_by_locator(self, scope: TenantScope, locator: str) -> CompanySource | None: ...

    async def upsert(self, scope: TenantScope, source: CompanySource) -> CompanySource: ...


class PersonRepository(Protocol):
    async def get(self, scope: TenantScope, person_id: PersonId) -> Person | None: ...

    async def upsert(self, scope: TenantScope, person: Person) -> Person: ...


class LeadRepository(Protocol):
    async def get(self, scope: TenantScope, lead_id: LeadId) -> Lead | None: ...

    async def list_for_workspace(
        self,
        scope: TenantScope,
        *,
        limit: int = 50,
        offset: int = 0,
        is_qualified: bool | None = None,
        classification: str | None = None,
    ) -> list[Lead]: ...

    async def get_by_company(self, scope: TenantScope, company_id: CompanyId) -> Lead | None: ...

    async def upsert(self, scope: TenantScope, lead: Lead) -> Lead: ...

    async def save_score(self, scope: TenantScope, record: LeadScoreRecord) -> None: ...


class EvidenceRepository(Protocol):
    async def get(self, scope: TenantScope, evidence_id: EvidenceId) -> Evidence | None: ...

    async def list_for_lead(self, scope: TenantScope, lead_id: LeadId) -> list[Evidence]: ...

    async def list_for_locator(self, scope: TenantScope, locator: str) -> list[Evidence]: ...

    async def list_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> list[Evidence]: ...

    async def add(self, scope: TenantScope, evidence: Evidence) -> Evidence: ...

    async def upsert(self, scope: TenantScope, evidence: Evidence) -> Evidence: ...


class SignalRepository(Protocol):
    async def list_for_company(self, scope: TenantScope, company_id: CompanyId) -> list[Signal]: ...

    async def get_by_company_and_type(
        self, scope: TenantScope, company_id: CompanyId, signal_type: SignalType
    ) -> Signal | None: ...

    async def upsert(self, scope: TenantScope, signal: Signal) -> Signal: ...

    async def delete(self, scope: TenantScope, signal_id: SignalId) -> None: ...


class JobQueue(Protocol):
    async def enqueue(
        self,
        scope: TenantScope,
        job_type: JobType,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> Job: ...

    async def claim(self, *, worker_id: str, now: datetime, lease_seconds: int) -> Job | None: ...

    async def complete(self, job: Job) -> None: ...

    async def fail(
        self, job: Job, error: str, *, now: datetime, permanent: bool = False
    ) -> Job: ...


class SourceAdapter(Protocol):
    adapter_key: str
    source_class: SourceClass

    async def fetch(self, request: FetchRequest) -> list[NormalizedRecord]: ...


class DiscoveryPort(Protocol):
    async def discover_companies(self, profile: SearchProfile) -> list[CompanyCandidate]: ...


class CompanyDiscoveryProvider(Protocol):
    provider_key: str

    async def discover(
        self,
        scope: TenantScope,
        request: DiscoveryRequest,
    ) -> list[ProviderDiscoveryHit]: ...


class NewsRecord:
    def __init__(
        self,
        *,
        fact: str,
        locator: str,
        snippet: str | None,
        collected_at: datetime,
        confidence: str,
        source_class: SourceClass,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.fact = fact
        self.locator = locator
        self.snippet = snippet
        self.collected_at = collected_at
        self.confidence = confidence
        self.source_class = source_class
        self.metadata = metadata or {}


class CompanyNewsProvider(Protocol):
    provider_key: str

    async def fetch_company_news(
        self,
        scope: TenantScope,
        company: Company,
    ) -> list[NewsRecord]: ...


class CompanyResearchCaseRepository(Protocol):
    async def create(
        self, scope: TenantScope, case: CompanyResearchCase
    ) -> CompanyResearchCase: ...

    async def update(
        self, scope: TenantScope, case: CompanyResearchCase
    ) -> CompanyResearchCase: ...

    async def get(self, scope: TenantScope, case_id: UUID) -> CompanyResearchCase | None: ...

    async def get_latest_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> CompanyResearchCase | None: ...


class ResearchPageRepository(Protocol):
    async def create(self, scope: TenantScope, page: ResearchPage) -> ResearchPage: ...

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[ResearchPage]: ...


class CompanyFactRepository(Protocol):
    async def upsert(self, scope: TenantScope, fact: CompanyFact) -> tuple[CompanyFact, bool]: ...

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[CompanyFact]: ...

    async def list_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> list[CompanyFact]: ...


class EvidenceFactExtractor(Protocol):
    extraction_method: str

    def extract(self, contexts: list[EvidencePageContext]) -> list[ExtractedCompanyFact]: ...


class ImportBatchRepository(Protocol):
    async def create(self, scope: TenantScope, batch: ImportBatch) -> ImportBatch: ...

    async def update(self, scope: TenantScope, batch: ImportBatch) -> ImportBatch: ...

    async def get(self, scope: TenantScope, batch_id: ImportBatchId) -> ImportBatch | None: ...


class ImportedProspectRepository(Protocol):
    async def create(self, scope: TenantScope, prospect: ImportedProspect) -> ImportedProspect: ...

    async def update(self, scope: TenantScope, prospect: ImportedProspect) -> ImportedProspect: ...

    async def get(
        self, scope: TenantScope, prospect_id: ImportedProspectId
    ) -> ImportedProspect | None: ...

    async def find_by_duplicate_key(
        self, scope: TenantScope, duplicate_key: str | None
    ) -> ImportedProspect | None: ...

    async def list_for_tenant(
        self,
        scope: TenantScope,
        *,
        batch_id: ImportBatchId | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ImportedProspect]: ...

    async def list_for_batch(
        self, scope: TenantScope, batch_id: ImportBatchId
    ) -> list[ImportedProspect]: ...


class DiscoveryCandidateRepository(Protocol):
    async def upsert(
        self, scope: TenantScope, candidate: DiscoveryCandidate
    ) -> DiscoveryCandidate: ...

    async def list_for_job(self, scope: TenantScope, job_id: JobId) -> list[DiscoveryCandidate]: ...

    async def get_by_locator(
        self, scope: TenantScope, job_id: JobId, source_locator: str
    ) -> DiscoveryCandidate | None: ...

    async def get_by_id(
        self, scope: TenantScope, candidate_id: UUID
    ) -> DiscoveryCandidate | None: ...

    async def find_by_id(self, candidate_id: UUID) -> DiscoveryCandidate | None: ...

    async def get_by_fetch_job_id(
        self, scope: TenantScope, fetch_job_id: JobId
    ) -> DiscoveryCandidate | None: ...

    async def list_for_tenant(
        self,
        scope: TenantScope,
        *,
        ingestion_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiscoveryCandidate]: ...


class NotificationPort(Protocol):
    async def send(self, channel: str, title: str, body: str, payload: dict[str, Any]) -> None: ...


class AIGateway(Protocol):
    async def complete(self, request: AIRequest) -> AIResponse: ...


class FetchRequest:
    def __init__(
        self,
        scope: TenantScope,
        locator: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.scope = scope
        self.locator = locator
        self.metadata = metadata or {}


class NormalizedRecord:
    def __init__(
        self,
        fact: str,
        locator: str,
        snippet: str | None,
        collected_at: datetime,
        confidence: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.fact = fact
        self.locator = locator
        self.snippet = snippet
        self.collected_at = collected_at
        self.confidence = confidence
        self.metadata = metadata or {}


class AIOperation:
    RESEARCH_SUMMARY = "research_summary"
    FACT_EXTRACTION = "fact_extraction"
    SIGNAL_EXTRACTION_ASSIST = "signal_extraction_assist"
    OUTREACH_DRAFT = "outreach_draft"


class AIRequest:
    def __init__(
        self,
        operation: str,
        tenant_id: UUID,
        authorized_context: dict[str, Any],
        allowed_evidence_ids: list[str],
    ) -> None:
        self.operation = operation
        self.tenant_id = tenant_id
        self.authorized_context = authorized_context
        self.allowed_evidence_ids = allowed_evidence_ids


class AIResponse:
    def __init__(
        self,
        operation: str,
        content: dict[str, Any],
        cited_evidence_ids: list[str],
    ) -> None:
        self.operation = operation
        self.content = content
        self.cited_evidence_ids = cited_evidence_ids
