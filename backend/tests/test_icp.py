from __future__ import annotations

from prospectiq.domain.company import Company, CompanyType
from prospectiq.domain.icp import DEFAULT_ICP_RULESET
from prospectiq.domain.person import Person, Seniority


def test_matching_company_passes_icp(matching_company: Company) -> None:
    result = DEFAULT_ICP_RULESET.evaluate_company(matching_company)
    assert result.matches is True


def test_company_size_bounds(matching_company: Company) -> None:
    matching_company.employee_count = 10
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is False
    matching_company.employee_count = 11
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is True
    matching_company.employee_count = 1000
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is True
    matching_company.employee_count = 1001
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is False


def test_growth_hiring_and_type(matching_company: Company) -> None:
    matching_company.headcount_growth_pct = 9.9
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is False
    matching_company.headcount_growth_pct = 10.0
    matching_company.is_hiring = False
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is False
    matching_company.is_hiring = True
    matching_company.company_type = CompanyType.PRIVATELY_HELD
    assert DEFAULT_ICP_RULESET.evaluate_company(matching_company).matches is True


def test_decision_maker_and_manager_exception(
    matching_person: Person, matching_company: Company
) -> None:
    assert (
        DEFAULT_ICP_RULESET.evaluate_decision_maker(
            matching_person, company_employee_count=matching_company.employee_count
        ).matches
        is True
    )
    matching_person.seniority = Seniority.MANAGER
    assert (
        DEFAULT_ICP_RULESET.evaluate_decision_maker(
            matching_person, company_employee_count=199
        ).matches
        is True
    )
    assert (
        DEFAULT_ICP_RULESET.evaluate_decision_maker(
            matching_person, company_employee_count=200
        ).matches
        is False
    )
