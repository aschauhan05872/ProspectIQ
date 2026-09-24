"""Audit events for security and process traceability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from prospectiq.domain.common import TenantId, UserId


@dataclass(slots=True)
class AuditEvent:
    id: UUID
    tenant_id: TenantId
    action: str
    entity_type: str
    entity_id: str
    actor_user_id: UserId | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
