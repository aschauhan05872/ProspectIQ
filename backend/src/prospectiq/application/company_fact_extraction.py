"""Structured evidence analysis — derive traceable company facts (Phase 5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from prospectiq.application.ports import (
    CompanyFactRepository,
    CompanyResearchCaseRepository,
    EvidenceFactExtractor,
    EvidenceRepository,
    JobQueue,
    ResearchPageRepository,
)
from prospectiq.domain.common import CompanyFactId, CompanyId, TenantScope, utcnow
from prospectiq.domain.company_facts import (
    COMPANY_FACT_EXTRACTION_VERSION,
    CompanyFact,
    CompanyFactExtractionResult,
    CompanyFactExtractionSubmission,
    CompanyFactStatus,
    EvidencePageContext,
    ExtractedCompanyFact,
    PermanentCompanyFactError,
    extract_facts_job_idempotency_key,
)
from prospectiq.domain.company_research import CompanyResearchStatus, ResearchPageFetchStatus
from prospectiq.domain.evidence import EvidenceOrigin
from prospectiq.domain.ingestion import SourceFactKind
from prospectiq.domain.jobs import Job, JobType
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.company_fact_extraction")


class CompanyFactExtractionService:
    def __init__(
        self,
        *,
        cases: CompanyResearchCaseRepository,
        pages: ResearchPageRepository,
        evidence: EvidenceRepository,
        facts: CompanyFactRepository,
        jobs: JobQueue,
        extractor: EvidenceFactExtractor,
    ) -> None:
        self._cases = cases
        self._pages = pages
        self._evidence = evidence
        self._facts = facts
        self._jobs = jobs
        self._extractor = extractor

    async def submit_for_case(
        self, scope: TenantScope, case_id: UUID
    ) -> CompanyFactExtractionSubmission:
        _assert_tenant(scope)
        case = await self._cases.get(scope, case_id)
        if case is None:
            raise PermanentCompanyFactError("Research case not found.")
        if case.status not in {
            CompanyResearchStatus.COMPLETED,
        }:
            raise PermanentCompanyFactError(
                "Research case must be completed before fact extraction."
            )
        if case.pages_fetched < 1:
            raise PermanentCompanyFactError(
                "Research case has no fetched pages to extract facts from."
            )

        payload: dict[str, Any] = {
            "research_case_id": str(case_id),
            "company_id": str(case.company_id),
        }
        job = await self._jobs.enqueue(
            scope,
            JobType.EXTRACT_COMPANY_FACTS,
            extract_facts_job_idempotency_key(case_id),
            payload,
        )
        logger.info(
            "company_fact_extraction_submitted",
            tenant_id=str(scope.tenant_id),
            case_id=str(case_id),
            job_id=str(job.id),
        )
        return CompanyFactExtractionSubmission(
            job_id=job.id,
            research_case_id=case_id,
            already_enqueued=bool(job.extra.get("idempotent_replay")),
        )

    async def execute_job(self, job: Job) -> CompanyFactExtractionResult:
        scope = TenantScope(tenant_id=job.tenant_id, job_id=str(job.id))
        case_id = UUID(str(job.payload["research_case_id"]))
        company_id = CompanyId(UUID(str(job.payload["company_id"])))
        case = await self._cases.get(scope, case_id)
        if case is None:
            raise PermanentCompanyFactError("Research case not found.")
        if case.company_id != company_id:
            raise PermanentCompanyFactError("Research case company mismatch.")

        contexts = await self._build_contexts(scope, case_id, company_id)
        if not contexts:
            raise PermanentCompanyFactError("No research evidence available for extraction.")

        extracted = self._extractor.extract(contexts)
        created = 0
        updated = 0
        now = utcnow()
        for item in extracted:
            fact = self._to_company_fact(
                scope=scope,
                case_id=case_id,
                company_id=company_id,
                extracted=item,
                now=now,
            )
            _, is_new = await self._facts.upsert(scope, fact)
            if is_new:
                created += 1
            else:
                updated += 1

        stored = await self._facts.list_for_case(scope, case_id)
        logger.info(
            "company_fact_extraction_completed",
            tenant_id=str(scope.tenant_id),
            case_id=str(case_id),
            created=created,
            updated=updated,
            total=len(stored),
        )
        return CompanyFactExtractionResult(
            research_case_id=case_id,
            company_id=company_id,
            facts_created=created,
            facts_updated=updated,
            facts_total=len(stored),
        )

    async def list_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> list[CompanyFact]:
        _assert_tenant(scope)
        return await self._facts.list_for_company(scope, company_id)

    async def list_for_case(self, scope: TenantScope, case_id: UUID) -> list[CompanyFact]:
        _assert_tenant(scope)
        case = await self._cases.get(scope, case_id)
        if case is None:
            raise PermanentCompanyFactError("Research case not found.")
        return await self._facts.list_for_case(scope, case_id)

    async def _build_contexts(
        self,
        scope: TenantScope,
        case_id: UUID,
        company_id: CompanyId,
    ) -> list[EvidencePageContext]:
        pages = await self._pages.list_for_case(scope, case_id)
        evidence_rows = await self._evidence.list_for_company(scope, company_id)
        evidence_by_id = {item.id: item for item in evidence_rows}
        contexts: list[EvidencePageContext] = []

        for page in pages:
            if page.fetch_status is not ResearchPageFetchStatus.SUCCEEDED:
                continue
            if page.evidence_id is None:
                continue
            evidence = evidence_by_id.get(page.evidence_id)
            if evidence is None:
                continue
            if evidence.origin is not EvidenceOrigin.SOURCE_DERIVED:
                continue
            if evidence.metadata.get("fact_kind") != SourceFactKind.RESEARCH_PAGE_CONTENT.value:
                continue
            if evidence.metadata.get("research_case_id") != str(case_id):
                continue
            text = page.normalized_text or evidence.snippet or evidence.fact
            contexts.append(
                EvidencePageContext(
                    evidence_id=evidence.id,
                    company_id=company_id,
                    source_locator=evidence.source_locator or page.normalized_url,
                    page_type=str(evidence.metadata.get("page_type") or page.page_type.value),
                    title=page.title or evidence.metadata.get("title"),
                    text=text,
                    metadata=dict(evidence.metadata),
                )
            )
        return contexts

    def _to_company_fact(
        self,
        *,
        scope: TenantScope,
        case_id: UUID,
        company_id: CompanyId,
        extracted: ExtractedCompanyFact,
        now: datetime,
    ) -> CompanyFact:
        extracted_at = now
        return CompanyFact(
            id=CompanyFactId(uuid4()),
            tenant_id=scope.tenant_id,
            company_id=company_id,
            research_case_id=case_id,
            category=extracted.category,
            subject=extracted.subject,
            value=extracted.value,
            evidence_ids=list(extracted.evidence_ids),
            origin=extracted.origin,
            confidence=extracted.confidence,
            extraction_method=self._extractor.extraction_method,
            extraction_version=COMPANY_FACT_EXTRACTION_VERSION,
            status=CompanyFactStatus.ACTIVE,
            dedupe_key=extracted.dedupe_key(),
            extracted_at=extracted_at,
            created_at=extracted_at,
            updated_at=extracted_at,
        )


def _assert_tenant(scope: TenantScope) -> None:
    if scope.tenant_id is None:
        raise PermanentCompanyFactError("Tenant context is required.")
