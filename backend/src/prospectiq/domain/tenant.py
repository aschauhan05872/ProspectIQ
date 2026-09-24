"""Tenant and workspace identity. V0 is single-tenant; the column still exists."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from prospectiq.domain.common import TenantId, WorkspaceId, utcnow


@dataclass(slots=True)
class Tenant:
    id: TenantId
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, tenant_id: TenantId, name: str, slug: str) -> Tenant:
        now = utcnow()
        return cls(id=tenant_id, name=name, slug=slug, created_at=now, updated_at=now)


@dataclass(slots=True)
class Workspace:
    id: WorkspaceId
    tenant_id: TenantId
    name: str
    created_at: datetime
    updated_at: datetime
