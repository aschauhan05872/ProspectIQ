from __future__ import annotations

from prospectiq.domain.company import Geography, Industry, normalize_geography, normalize_industry


def test_industry_aliases_from_sop() -> None:
    assert normalize_industry("HealthTech") is Industry.HEALTHCARE_HEALTHTECH
    assert normalize_industry("Fintech/Financial Services") is Industry.FINTECH_FINANCIAL_SERVICES
    assert normalize_industry("Retail & E-commerce") is Industry.RETAIL_ECOMMERCE
    assert normalize_industry("Telecom") is Industry.TELECOMMUNICATIONS
    assert normalize_industry("unknown") is None


def test_geography_aliases_from_sop() -> None:
    assert normalize_geography("USA") is Geography.USA
    assert normalize_geography("United Kingdom") is Geography.UK
    assert normalize_geography("Saudi Arabia") is Geography.UAE_SAUDI_QATAR
    assert normalize_geography("Canada") is Geography.CANADA
