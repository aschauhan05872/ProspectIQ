"""Internal user identity. Enterprise SSO is a later SaaS concern."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from prospectiq.domain.common import TenantId, UserId


class UserRole(StrEnum):
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    ADMIN = "admin"


@dataclass(slots=True)
class User:
    id: UserId
    tenant_id: TenantId
    email: str
    display_name: str
    role: UserRole
    created_at: datetime
    updated_at: datetime
