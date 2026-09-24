"""CSV field normalization and column mapping. No network I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from prospectiq.domain.company import normalize_geography, normalize_industry


class ProspectField(StrEnum):
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    FULL_NAME = "full_name"
    JOB_TITLE = "job_title"
    SENIORITY = "seniority"
    DEPARTMENT = "department"
    LINKEDIN_URL = "linkedin_url"
    EMAIL = "email"
    EMAIL_STATUS = "email_status"
    PHONE = "phone"
    COMPANY_NAME = "company_name"
    COMPANY_DOMAIN = "company_domain"
    WEBSITE = "website"
    COMPANY_LINKEDIN = "company_linkedin"
    INDUSTRY = "industry"
    COUNTRY = "country"
    CITY = "city"
    EMPLOYEE_COUNT = "employee_count"
    FUNDING = "funding"
    LATEST_FUNDING = "latest_funding"
    LATEST_FUNDING_DATE = "latest_funding_date"
    TECHNOLOGIES = "technologies"
    COMPANY_DESCRIPTION = "company_description"


# Provider-agnostic header aliases (Apollo, ZoomInfo-style exports, etc.)
HEADER_ALIASES: dict[str, ProspectField] = {
    "first name": ProspectField.FIRST_NAME,
    "firstname": ProspectField.FIRST_NAME,
    "last name": ProspectField.LAST_NAME,
    "lastname": ProspectField.LAST_NAME,
    "name": ProspectField.FULL_NAME,
    "full name": ProspectField.FULL_NAME,
    "contact name": ProspectField.FULL_NAME,
    "title": ProspectField.JOB_TITLE,
    "job title": ProspectField.JOB_TITLE,
    "seniority": ProspectField.SENIORITY,
    "departments": ProspectField.DEPARTMENT,
    "department": ProspectField.DEPARTMENT,
    "person linkedin url": ProspectField.LINKEDIN_URL,
    "linkedin url": ProspectField.LINKEDIN_URL,
    "linkedin": ProspectField.LINKEDIN_URL,
    "email": ProspectField.EMAIL,
    "email address": ProspectField.EMAIL,
    "email status": ProspectField.EMAIL_STATUS,
    "phone": ProspectField.PHONE,
    "phone number": ProspectField.PHONE,
    "company": ProspectField.COMPANY_NAME,
    "company name": ProspectField.COMPANY_NAME,
    "organization": ProspectField.COMPANY_NAME,
    "company domain": ProspectField.COMPANY_DOMAIN,
    "domain": ProspectField.COMPANY_DOMAIN,
    "website": ProspectField.WEBSITE,
    "company website": ProspectField.WEBSITE,
    "company linkedin url": ProspectField.COMPANY_LINKEDIN,
    "company linkedin": ProspectField.COMPANY_LINKEDIN,
    "industry": ProspectField.INDUSTRY,
    "country": ProspectField.COUNTRY,
    "company country": ProspectField.COUNTRY,
    "city": ProspectField.CITY,
    "company city": ProspectField.CITY,
    "# employees": ProspectField.EMPLOYEE_COUNT,
    "employees": ProspectField.EMPLOYEE_COUNT,
    "employee count": ProspectField.EMPLOYEE_COUNT,
    "total funding": ProspectField.FUNDING,
    "funding": ProspectField.FUNDING,
    "latest funding": ProspectField.LATEST_FUNDING,
    "latest funding amount": ProspectField.LATEST_FUNDING,
    "latest funding date": ProspectField.LATEST_FUNDING_DATE,
    "technologies": ProspectField.TECHNOLOGIES,
    "tech stack": ProspectField.TECHNOLOGIES,
    "company description": ProspectField.COMPANY_DESCRIPTION,
    "description": ProspectField.COMPANY_DESCRIPTION,
}

CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True, slots=True)
class ColumnMappingResult:
    mapping: dict[str, ProspectField]
    unmapped_headers: tuple[str, ...]
    detected_headers: tuple[str, ...]


def sanitize_csv_cell(value: str | None) -> str | None:
    """Prevent CSV formula injection when values are re-exported or displayed."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip().lower())


def detect_column_mapping(headers: list[str]) -> ColumnMappingResult:
    mapping: dict[str, ProspectField] = {}
    unmapped: list[str] = []
    for header in headers:
        key = normalize_header(header)
        field = HEADER_ALIASES.get(key)
        if field is None:
            unmapped.append(header)
        else:
            mapping[header] = field
    return ColumnMappingResult(
        mapping=mapping,
        unmapped_headers=tuple(unmapped),
        detected_headers=tuple(headers),
    )


def normalize_domain(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    text = sanitize_csv_cell(str(raw).strip()) or ""
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    text = text.split("/")[0].lower().strip()
    if not text or "." not in text:
        return None
    return text


def normalize_website_url(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    text = sanitize_csv_cell(str(raw).strip()) or ""
    if not text.startswith(("http://", "https://")):
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return text.rstrip("/")


def normalize_linkedin_url(raw: str | None) -> str | None:
    """Store LinkedIn URL as metadata only — never scraped."""
    if not raw or not str(raw).strip():
        return None
    text = sanitize_csv_cell(str(raw).strip()) or ""
    if "linkedin.com" not in text.lower():
        return None
    if not text.startswith(("http://", "https://")):
        text = f"https://{text}"
    return text.rstrip("/")


def parse_employee_count(raw: str | None) -> int | None:
    if not raw or not str(raw).strip():
        return None
    text = re.sub(r"[^\d]", "", str(raw))
    if not text:
        return None
    value = int(text)
    return value if value > 0 else None


def normalize_company_name(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    return sanitize_csv_cell(str(raw).strip())


def normalize_person_name(
    *,
    first_name: str | None,
    last_name: str | None,
    full_name: str | None,
) -> str | None:
    if full_name and full_name.strip():
        return sanitize_csv_cell(full_name.strip())
    parts = [part for part in (first_name, last_name) if part and part.strip()]
    if parts:
        return sanitize_csv_cell(" ".join(parts))
    return None


def normalize_email(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    text = sanitize_csv_cell(str(raw).strip()) or ""
    if "@" not in text or " " in text:
        return None
    return text.lower()


def map_row_to_fields(
    row: dict[str, str],
    mapping: dict[str, ProspectField],
) -> dict[str, Any]:
    """Map a CSV row to normalized prospect fields."""
    raw_by_field: dict[ProspectField, str] = {}
    for header, value in row.items():
        field = mapping.get(header)
        if field is None:
            continue
        cleaned = sanitize_csv_cell(value)
        if cleaned:
            raw_by_field[field] = cleaned

    first = raw_by_field.get(ProspectField.FIRST_NAME)
    last = raw_by_field.get(ProspectField.LAST_NAME)
    full = raw_by_field.get(ProspectField.FULL_NAME)

    domain = normalize_domain(
        raw_by_field.get(ProspectField.COMPANY_DOMAIN)
        or raw_by_field.get(ProspectField.WEBSITE)
    )
    website = normalize_website_url(raw_by_field.get(ProspectField.WEBSITE))
    if domain is None and website:
        domain = normalize_domain(website)

    industry_raw = raw_by_field.get(ProspectField.INDUSTRY)
    parsed_industry = normalize_industry(industry_raw) if industry_raw else None
    industry = parsed_industry.value if parsed_industry else industry_raw

    country_raw = raw_by_field.get(ProspectField.COUNTRY)
    parsed_geo = normalize_geography(country_raw) if country_raw else None
    geography = parsed_geo.value if parsed_geo else country_raw

    return {
        "first_name": first,
        "last_name": last,
        "full_name": normalize_person_name(first_name=first, last_name=last, full_name=full),
        "job_title": raw_by_field.get(ProspectField.JOB_TITLE),
        "seniority": raw_by_field.get(ProspectField.SENIORITY),
        "department": raw_by_field.get(ProspectField.DEPARTMENT),
        "linkedin_url": normalize_linkedin_url(raw_by_field.get(ProspectField.LINKEDIN_URL)),
        "email": normalize_email(raw_by_field.get(ProspectField.EMAIL)),
        "email_status": raw_by_field.get(ProspectField.EMAIL_STATUS),
        "phone": raw_by_field.get(ProspectField.PHONE),
        "company_name": normalize_company_name(raw_by_field.get(ProspectField.COMPANY_NAME)),
        "company_domain": domain,
        "website": website,
        "company_linkedin": normalize_linkedin_url(
            raw_by_field.get(ProspectField.COMPANY_LINKEDIN)
        ),
        "industry": industry,
        "country": geography,
        "city": raw_by_field.get(ProspectField.CITY),
        "employee_count": parse_employee_count(raw_by_field.get(ProspectField.EMPLOYEE_COUNT)),
        "funding": raw_by_field.get(ProspectField.FUNDING),
        "latest_funding": raw_by_field.get(ProspectField.LATEST_FUNDING),
        "latest_funding_date": raw_by_field.get(ProspectField.LATEST_FUNDING_DATE),
        "technologies": raw_by_field.get(ProspectField.TECHNOLOGIES),
        "company_description": raw_by_field.get(ProspectField.COMPANY_DESCRIPTION),
    }


def duplicate_key(normalized: dict[str, Any]) -> str | None:
    """Key for duplicate detection within tenant."""
    email = normalized.get("email")
    if email:
        return f"email:{email.lower()}"
    domain = normalized.get("company_domain")
    name = normalized.get("full_name")
    if domain and name:
        return f"domain_name:{domain}:{name.lower()}"
    return None
