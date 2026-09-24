from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from prospectiq.api.main import create_app
from prospectiq.domain.common import TenantId, TenantScope
from prospectiq.domain.company import Company
from prospectiq.infrastructure.repositories import TenantMismatchError, _require_scope


def test_repository_refuses_cross_tenant_write(matching_company: Company) -> None:
    other = TenantScope(tenant_id=TenantId(UUID("00000000-0000-0000-0000-000000000099")))
    with pytest.raises(TenantMismatchError):
        _require_scope(other, matching_company.tenant_id)


def test_app_factory_exposes_tdd_routes() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    for required in (
        "/health",
        "/ready",
        "/searches",
        "/leads",
        "/research",
        "/drafts",
        "/activities",
        "/followups",
        "/notifications",
        "/sources/company",
        "/research/company",
        "/companies/{company_id}/research",
        "/companies/{company_id}/facts",
        "/research/cases/{case_id}",
        "/research/cases/{case_id}/facts",
        "/research/cases/{case_id}/extract-facts",
        "/discovery/companies",
    ):
        assert required in paths


def test_health_does_not_need_database() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_distinct_tenants_keep_separate_ids() -> None:
    a = TenantId(uuid4())
    b = TenantId(uuid4())
    assert a != b
