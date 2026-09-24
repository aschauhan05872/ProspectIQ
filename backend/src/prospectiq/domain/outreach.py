"""Outreach drafts, human activity, and follow-up windows from the Outreach SOP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from prospectiq.domain.common import EvidenceId, LeadId, TenantId, UserId
from prospectiq.domain.compliance import HumanControlledAction
from prospectiq.domain.pipeline import LeadStatus, should_stop_automated_follow_ups

FOLLOW_UP_SCHEDULE_VERSION = "sop-outreach-v1"


class ActorType(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"


class DraftType(StrEnum):
    CONNECTION_REQUEST = "connection_request"
    FIRST_MESSAGE = "first_message"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    FOLLOW_UP_3 = "follow_up_3"
    GENERIC_POST_ENGAGEMENT = "generic_post_engagement"
    CURIOSITY_SALES_NAVIGATOR = "curiosity_sales_navigator"


class OutreachRegion(StrEnum):
    NORTH_AMERICA = "north_america"
    UK_IRELAND = "uk_ireland"
    EUROPE = "europe"
    MIDDLE_EAST = "middle_east"
    ASIA_PACIFIC = "asia_pacific"


class FollowUpTaskStatus(StrEnum):
    SCHEDULED = "scheduled"
    DUE = "due"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActivityType(StrEnum):
    RESEARCH_COMPLETED = "research_completed"
    DRAFT_GENERATED = "draft_generated"
    OPENED_LINKEDIN = "opened_linkedin"
    VERIFIED_PROFILE = "verified_profile"
    CONNECTION_REQUEST_SENT = "connection_request_sent"
    MESSAGE_SENT = "message_sent"
    CONVERSATION_UPDATED = "conversation_updated"
    REPLY_RECEIVED = "reply_received"
    MEETING_BOOKED = "meeting_booked"
    STRATEGY_SHEET_UPDATED = "strategy_sheet_updated"
    FOLLOW_UP_CANCELLED = "follow_up_cancelled"
    STOP_REQUESTED = "stop_requested"


HUMAN_ACTIVITY_TYPES: frozenset[ActivityType] = frozenset(
    {
        ActivityType.OPENED_LINKEDIN,
        ActivityType.VERIFIED_PROFILE,
        ActivityType.CONNECTION_REQUEST_SENT,
        ActivityType.MESSAGE_SENT,
        ActivityType.CONVERSATION_UPDATED,
        ActivityType.REPLY_RECEIVED,
        ActivityType.MEETING_BOOKED,
        ActivityType.STRATEGY_SHEET_UPDATED,
        ActivityType.STOP_REQUESTED,
    }
)

ACTIVITY_TO_HUMAN_ACTION: dict[ActivityType, HumanControlledAction] = {
    ActivityType.OPENED_LINKEDIN: HumanControlledAction.OPEN_LINKEDIN,
    ActivityType.VERIFIED_PROFILE: HumanControlledAction.VERIFY_PERSON_OR_COMPANY,
    ActivityType.CONNECTION_REQUEST_SENT: HumanControlledAction.SEND_CONNECTION_REQUEST,
    ActivityType.MESSAGE_SENT: HumanControlledAction.SEND_LINKEDIN_MESSAGE,
    ActivityType.CONVERSATION_UPDATED: HumanControlledAction.READ_OR_RESPOND_TO_CONVERSATION,
    ActivityType.REPLY_RECEIVED: HumanControlledAction.READ_OR_RESPOND_TO_CONVERSATION,
    ActivityType.MEETING_BOOKED: HumanControlledAction.DECIDE_WHETHER_TO_PURSUE,
}


@dataclass(frozen=True, slots=True)
class BusinessDayWindow:
    """SOP uses ranges, not a single invented day count."""

    min_business_days: int
    max_business_days: int


FOLLOW_UP_WINDOWS: dict[LeadStatus, BusinessDayWindow] = {
    LeadStatus.FOLLOW_UP_1: BusinessDayWindow(2, 3),
    LeadStatus.FOLLOW_UP_2: BusinessDayWindow(3, 5),
    LeadStatus.FOLLOW_UP_3: BusinessDayWindow(4, 7),
}

NURTURE_WINDOW = BusinessDayWindow(30, 60)


def add_business_days(start: date, business_days: int) -> date:
    remaining = business_days
    current = start
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


@dataclass(frozen=True, slots=True)
class FollowUpSchedule:
    stage: LeadStatus
    earliest_date: date
    latest_date: date
    ruleset_version: str = FOLLOW_UP_SCHEDULE_VERSION


class FollowUpScheduler:
    version = FOLLOW_UP_SCHEDULE_VERSION

    def schedule(
        self,
        *,
        next_stage: LeadStatus,
        after: date,
        lead_status: LeadStatus,
    ) -> FollowUpSchedule | None:
        if should_stop_automated_follow_ups(lead_status):
            return None
        window = FOLLOW_UP_WINDOWS.get(next_stage)
        if window is None:
            return None
        return FollowUpSchedule(
            stage=next_stage,
            earliest_date=add_business_days(after, window.min_business_days),
            latest_date=add_business_days(after, window.max_business_days),
        )


DEFAULT_FOLLOW_UP_SCHEDULER = FollowUpScheduler()


@dataclass(slots=True)
class MessageDraft:
    id: UUID
    tenant_id: TenantId
    lead_id: LeadId
    draft_type: DraftType
    region: OutreachRegion | None
    body: str
    evidence_ids: list[EvidenceId]
    created_at: datetime


@dataclass(slots=True)
class Activity:
    id: UUID
    tenant_id: TenantId
    lead_id: LeadId
    activity_type: ActivityType
    actor_type: ActorType
    actor_user_id: UserId | None
    occurred_at: datetime
    notes: str | None


@dataclass(slots=True)
class FollowUpTask:
    id: UUID
    tenant_id: TenantId
    lead_id: LeadId
    stage: LeadStatus
    earliest_date: date
    latest_date: date
    status: FollowUpTaskStatus
    cancelled_reason: str | None
    created_at: datetime
    updated_at: datetime
