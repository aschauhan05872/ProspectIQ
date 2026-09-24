"""Company and company-source records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from prospectiq.domain.common import CompanyId, TenantId
from prospectiq.domain.source_registry import SourceClass


class CompanyType(StrEnum):
    PRIVATELY_HELD = "privately_held"
    PUBLIC_COMPANY = "public_company"
    VENTURE_BACKED = "venture_backed"


class Industry(StrEnum):
    HEALTHCARE_HEALTHTECH = "healthcare_healthtech"
    FINTECH_FINANCIAL_SERVICES = "fintech_financial_services"
    INSURANCE = "insurance"
    RETAIL_ECOMMERCE = "retail_ecommerce"
    TELECOMMUNICATIONS = "telecommunications"
    MANUFACTURING = "manufacturing"
    LOGISTICS_SUPPLY_CHAIN = "logistics_supply_chain"
    TRAVEL_HOSPITALITY = "travel_hospitality"


class Geography(StrEnum):
    USA = "usa"
    UK = "uk"
    EUROPE = "europe"
    UAE_SAUDI_QATAR = "uae_saudi_qatar"
    AUSTRALIA = "australia"
    CANADA = "canada"


INDUSTRY_ALIASES: dict[str, Industry] = {
    "healthcare": Industry.HEALTHCARE_HEALTHTECH,
    "healthtech": Industry.HEALTHCARE_HEALTHTECH,
    "healthcare / healthtech": Industry.HEALTHCARE_HEALTHTECH,
    "fintech": Industry.FINTECH_FINANCIAL_SERVICES,
    "financial services": Industry.FINTECH_FINANCIAL_SERVICES,
    "fintech/financial services": Industry.FINTECH_FINANCIAL_SERVICES,
    "insurance": Industry.INSURANCE,
    "retail": Industry.RETAIL_ECOMMERCE,
    "e-commerce": Industry.RETAIL_ECOMMERCE,
    "ecommerce": Industry.RETAIL_ECOMMERCE,
    "retail & e-commerce": Industry.RETAIL_ECOMMERCE,
    "retail/e-commerce": Industry.RETAIL_ECOMMERCE,
    "telecom": Industry.TELECOMMUNICATIONS,
    "telecommunications": Industry.TELECOMMUNICATIONS,
    "manufacturing": Industry.MANUFACTURING,
    "logistics": Industry.LOGISTICS_SUPPLY_CHAIN,
    "supply chain": Industry.LOGISTICS_SUPPLY_CHAIN,
    "logistics & supply chain": Industry.LOGISTICS_SUPPLY_CHAIN,
    "logistics/supply chain": Industry.LOGISTICS_SUPPLY_CHAIN,
    "travel": Industry.TRAVEL_HOSPITALITY,
    "hospitality": Industry.TRAVEL_HOSPITALITY,
    "travel & hospitality": Industry.TRAVEL_HOSPITALITY,
    "travel/hospitality": Industry.TRAVEL_HOSPITALITY,
}

GEOGRAPHY_ALIASES: dict[str, Geography] = {
    "usa": Geography.USA,
    "united states": Geography.USA,
    "us": Geography.USA,
    "uk": Geography.UK,
    "united kingdom": Geography.UK,
    "ireland": Geography.UK,
    "europe": Geography.EUROPE,
    "uae": Geography.UAE_SAUDI_QATAR,
    "saudi arabia": Geography.UAE_SAUDI_QATAR,
    "qatar": Geography.UAE_SAUDI_QATAR,
    "uae / saudi arabia / qatar": Geography.UAE_SAUDI_QATAR,
    "australia": Geography.AUSTRALIA,
    "canada": Geography.CANADA,
}


def normalize_industry(value: str) -> Industry | None:
    return INDUSTRY_ALIASES.get(value.strip().lower())


def normalize_geography(value: str) -> Geography | None:
    return GEOGRAPHY_ALIASES.get(value.strip().lower())


@dataclass(slots=True)
class Company:
    id: CompanyId
    tenant_id: TenantId
    name: str
    normalized_name: str
    website: str | None
    industry: Industry | None
    geography: Geography | None
    employee_count: int | None
    headcount_growth_pct: float | None
    company_type: CompanyType | None
    is_hiring: bool | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class CompanySource:
    id: UUID
    tenant_id: TenantId
    company_id: CompanyId
    source_class: SourceClass
    locator: str
    raw_reference: str | None
    collected_at: datetime
