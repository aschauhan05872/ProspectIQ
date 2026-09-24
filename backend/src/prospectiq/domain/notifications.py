"""Notification records. Delivery is an infrastructure adapter concern."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from prospectiq.domain.common import LeadId, TenantId


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    TELEGRAM = "telegram"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(slots=True)
class Notification:
    id: UUID
    tenant_id: TenantId
    channel: NotificationChannel
    title: str
    body: str
    status: NotificationStatus
    lead_id: LeadId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    sent_at: datetime | None = None
