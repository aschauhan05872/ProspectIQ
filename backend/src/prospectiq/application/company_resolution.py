"""Resolve imported prospects to Company + Person records."""

from __future__ import annotations

from uuid import uuid4

from prospectiq.application.ports import (
    CompanyRepository,
    ImportedProspectRepository,
    PersonRepository,
)
from prospectiq.domain.common import CompanyId, PersonId, TenantScope, utcnow
from prospectiq.domain.company import Company, CompanyType, Geography, Industry
from prospectiq.domain.company_resolution import CompanyResolutionResult, plan_company_resolution
from prospectiq.domain.person import Person
from prospectiq.domain.prospect_import import ImportedProspect, ResolutionStatus
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.company_resolution")


class CompanyResolutionService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        persons: PersonRepository,
        prospects: ImportedProspectRepository,
    ) -> None:
        self._companies = companies
        self._persons = persons
        self._prospects = prospects

    async def resolve_prospect(
        self, scope: TenantScope, prospect: ImportedProspect
    ) -> CompanyResolutionResult:
        plan = plan_company_resolution(prospect.normalized_data)

        if plan.status in {ResolutionStatus.NOT_FOUND, ResolutionStatus.MANUAL_REVIEW}:
            prospect.resolution_status = plan.status
            prospect.updated_at = utcnow()
            await self._prospects.update(scope, prospect)
            return CompanyResolutionResult(
                company_id=None,
                status=plan.status,
                method=plan.method,
                created_new=False,
                notes=plan.notes,
            )

        assert plan.normalized_domain is not None
        existing = await self._companies.get_by_normalized_name(scope, plan.normalized_domain)
        created_new = existing is None
        now = utcnow()

        if existing is None:
            data = prospect.normalized_data
            industry_raw = data.get("industry")
            industry = None
            if industry_raw:
                try:
                    industry = Industry(str(industry_raw))
                except ValueError:
                    industry = None
            geo_raw = data.get("country")
            geography = None
            if geo_raw:
                try:
                    geography = Geography(str(geo_raw))
                except ValueError:
                    geography = None

            company = Company(
                id=CompanyId(uuid4()),
                tenant_id=scope.tenant_id,
                name=data.get("company_name") or plan.normalized_domain,
                normalized_name=plan.normalized_domain,
                website=plan.normalized_website,
                industry=industry,
                geography=geography,
                employee_count=data.get("employee_count"),
                headcount_growth_pct=None,
                company_type=CompanyType.PRIVATELY_HELD,
                is_hiring=None,
                created_at=now,
                updated_at=now,
            )
            company = await self._companies.upsert(scope, company)
        else:
            company = existing
            data = prospect.normalized_data
            if data.get("company_name") and existing.name == existing.normalized_name:
                existing.name = str(data["company_name"])
            if data.get("employee_count") and existing.employee_count is None:
                existing.employee_count = data["employee_count"]
            if data.get("website") and not existing.website:
                existing.website = plan.normalized_website
            existing.updated_at = now
            company = await self._companies.upsert(scope, existing)

        person = await self._upsert_person(scope, company.id, prospect.normalized_data)

        prospect.company_id = company.id
        prospect.person_id = person.id if person else None
        prospect.resolution_status = ResolutionStatus.RESOLVED
        prospect.updated_at = now
        await self._prospects.update(scope, prospect)

        logger.info(
            "company_resolved",
            tenant_id=str(scope.tenant_id),
            prospect_id=str(prospect.id),
            company_id=str(company.id),
            method=plan.method.value,
            created_new=created_new,
        )
        return CompanyResolutionResult(
            company_id=company.id,
            status=ResolutionStatus.RESOLVED,
            method=plan.method,
            created_new=created_new,
            notes=plan.notes,
        )

    async def resolve_batch(
        self, scope: TenantScope, prospects: list[ImportedProspect]
    ) -> dict[str, int]:
        """Resolve unique companies once per batch — skip duplicate company domains."""
        seen_domains: set[str] = set()
        stats = {"resolved": 0, "skipped": 0, "manual_review": 0, "not_found": 0}
        for prospect in prospects:
            if prospect.status.value != "imported":
                stats["skipped"] += 1
                continue
            domain = prospect.normalized_data.get("company_domain")
            if domain and domain in seen_domains:
                existing_company = await self._companies.get_by_normalized_name(scope, domain)
                if existing_company and prospect.company_id is None:
                    person = await self._upsert_person(
                        scope, existing_company.id, prospect.normalized_data
                    )
                    prospect.company_id = existing_company.id
                    prospect.person_id = person.id if person else None
                    prospect.resolution_status = ResolutionStatus.RESOLVED
                    prospect.updated_at = utcnow()
                    await self._prospects.update(scope, prospect)
                    stats["resolved"] += 1
                else:
                    stats["skipped"] += 1
                continue
            if domain:
                seen_domains.add(domain)

            result = await self.resolve_prospect(scope, prospect)
            if result.status is ResolutionStatus.RESOLVED:
                stats["resolved"] += 1
            elif result.status is ResolutionStatus.MANUAL_REVIEW:
                stats["manual_review"] += 1
            else:
                stats["not_found"] += 1
        return stats

    async def _upsert_person(
        self,
        scope: TenantScope,
        company_id: CompanyId,
        data: dict[str, object],
    ) -> Person | None:
        full_name = data.get("full_name")
        if not full_name or not str(full_name).strip():
            return None
        now = utcnow()
        person = Person(
            id=PersonId(uuid4()),
            tenant_id=scope.tenant_id,
            company_id=company_id,
            full_name=str(full_name).strip(),
            title=str(data["job_title"]) if data.get("job_title") else None,
            function=None,
            seniority=None,
            location=str(data["city"]) if data.get("city") else None,
            years_in_role=None,
            created_at=now,
            updated_at=now,
        )
        return await self._persons.upsert(scope, person)
