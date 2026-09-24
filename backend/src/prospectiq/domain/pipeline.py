"""Lead lifecycle aligned to the Outreach SOP sequence."""

from __future__ import annotations

from enum import StrEnum


class LeadStatus(StrEnum):
    NEW = "new"
    RESEARCH = "research"
    CONNECT = "connect"
    ENGAGE = "engage"
    FIRST_MESSAGE = "first_message"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    FOLLOW_UP_3 = "follow_up_3"
    QUALIFICATION = "qualification"
    MEETING_NEXT_STEP = "meeting_next_step"
    STRATEGY_SHEET = "strategy_sheet"
    ENGAGED = "engaged"
    NURTURE = "nurture"
    STOPPED = "stopped"


OUTREACH_SEQUENCE: tuple[LeadStatus, ...] = (
    LeadStatus.RESEARCH,
    LeadStatus.CONNECT,
    LeadStatus.ENGAGE,
    LeadStatus.FIRST_MESSAGE,
    LeadStatus.FOLLOW_UP_1,
    LeadStatus.FOLLOW_UP_2,
    LeadStatus.FOLLOW_UP_3,
    LeadStatus.QUALIFICATION,
    LeadStatus.MEETING_NEXT_STEP,
    LeadStatus.STRATEGY_SHEET,
)

# Automated-style follow-up stages that must stop once the prospect is engaged.
AUTOMATED_STYLE_FOLLOW_UP_STATUSES: frozenset[LeadStatus] = frozenset(
    {
        LeadStatus.FOLLOW_UP_1,
        LeadStatus.FOLLOW_UP_2,
        LeadStatus.FOLLOW_UP_3,
    }
)


def should_stop_automated_follow_ups(status: LeadStatus) -> bool:
    return status in {LeadStatus.ENGAGED, LeadStatus.STOPPED, LeadStatus.NURTURE}
