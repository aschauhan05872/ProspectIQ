"""Person / decision-maker records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from prospectiq.domain.common import CompanyId, PersonId, TenantId
from prospectiq.domain.source_registry import SourceClass


class DecisionFunction(StrEnum):
    ENGINEERING = "engineering"
    INFORMATION_TECHNOLOGY = "information_technology"
    PRODUCT = "product"
    OPERATIONS = "operations"
    BUSINESS_DEVELOPMENT = "business_development"


class Seniority(StrEnum):
    CXO = "cxo"
    VP = "vp"
    DIRECTOR = "director"
    HEAD = "head"
    PARTNER = "partner"
    OWNER = "owner"
    MANAGER = "manager"


# Sales Navigator SOP title-contains examples. Used for matching, not scoring.
TITLE_KEYWORDS: tuple[str, ...] = (
    "cto",
    "cio",
    "chief technology officer",
    "chief digital officer",
    "vp engineering",
    "vp technology",
    "director of engineering",
    "head of engineering",
    "head of technology",
    "it director",
    "chief product officer",
    "vp product",
    "director of product",
    "head of product",
    "digital transformation",
    "head of innovation",
    "head of ai",
    "head of automation",
    "coo",
    "head of operations",
    "director of operations",
)


@dataclass(slots=True)
class Person:
    id: PersonId
    tenant_id: TenantId
    company_id: CompanyId | None
    full_name: str
    title: str | None
    function: DecisionFunction | None
    seniority: Seniority | None
    location: str | None
    years_in_role: float | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class PersonSource:
    id: UUID
    tenant_id: TenantId
    person_id: PersonId
    source_class: SourceClass
    locator: str
    raw_reference: str | None
    collected_at: datetime
