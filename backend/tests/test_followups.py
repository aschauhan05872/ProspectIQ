from __future__ import annotations

from datetime import date

from prospectiq.domain.outreach import DEFAULT_FOLLOW_UP_SCHEDULER, add_business_days
from prospectiq.domain.pipeline import LeadStatus


def test_follow_up_windows_match_sop() -> None:
    after = date(2026, 9, 22)  # Tuesday
    first = DEFAULT_FOLLOW_UP_SCHEDULER.schedule(
        next_stage=LeadStatus.FOLLOW_UP_1,
        after=after,
        lead_status=LeadStatus.FIRST_MESSAGE,
    )
    assert first is not None
    assert first.earliest_date == add_business_days(after, 2)
    assert first.latest_date == add_business_days(after, 3)

    second = DEFAULT_FOLLOW_UP_SCHEDULER.schedule(
        next_stage=LeadStatus.FOLLOW_UP_2,
        after=first.earliest_date,
        lead_status=LeadStatus.FOLLOW_UP_1,
    )
    assert second is not None
    assert second.earliest_date == add_business_days(first.earliest_date, 3)
    assert second.latest_date == add_business_days(first.earliest_date, 5)

    third = DEFAULT_FOLLOW_UP_SCHEDULER.schedule(
        next_stage=LeadStatus.FOLLOW_UP_3,
        after=second.earliest_date,
        lead_status=LeadStatus.FOLLOW_UP_2,
    )
    assert third is not None
    assert third.earliest_date == add_business_days(second.earliest_date, 4)
    assert third.latest_date == add_business_days(second.earliest_date, 7)


def test_engaged_prospects_do_not_get_automated_follow_ups() -> None:
    result = DEFAULT_FOLLOW_UP_SCHEDULER.schedule(
        next_stage=LeadStatus.FOLLOW_UP_1,
        after=date(2026, 9, 22),
        lead_status=LeadStatus.ENGAGED,
    )
    assert result is None


def test_weekend_is_skipped_in_business_days() -> None:
    friday = date(2026, 9, 18)
    assert add_business_days(friday, 1) == date(2026, 9, 21)
