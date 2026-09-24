"""Ideal Customer Profile and decision-maker targeting from the SOPs/TDD."""

from __future__ import annotations

from dataclasses import dataclass

from prospectiq.domain.company import Company, CompanyType, Geography, Industry
from prospectiq.domain.person import DecisionFunction, Person, Seniority

ICP_RULESET_VERSION = "sop-lead-generation-v1"

MIN_EMPLOYEES = 11
MAX_EMPLOYEES = 1000
MIN_HEADCOUNT_GROWTH_PCT = 10.0
MANAGER_ALLOWED_BELOW_EMPLOYEES = 200

PRIORITY_INDUSTRIES: frozenset[Industry] = frozenset(Industry)
TARGET_GEOGRAPHIES: frozenset[Geography] = frozenset(Geography)
ALLOWED_COMPANY_TYPES: frozenset[CompanyType] = frozenset(CompanyType)
ALLOWED_FUNCTIONS: frozenset[DecisionFunction] = frozenset(DecisionFunction)
CORE_SENIORITY: frozenset[Seniority] = frozenset(
    {
        Seniority.CXO,
        Seniority.VP,
        Seniority.DIRECTOR,
        Seniority.HEAD,
        Seniority.PARTNER,
        Seniority.OWNER,
    }
)


@dataclass(frozen=True, slots=True)
class RuleCheck:
    code: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ICPEvaluation:
    matches: bool
    checks: tuple[RuleCheck, ...]
    ruleset_version: str = ICP_RULESET_VERSION


class ICPRuleset:
    version = ICP_RULESET_VERSION

    def evaluate_company(self, company: Company) -> ICPEvaluation:
        checks = (
            RuleCheck(
                "employee_size",
                company.employee_count is not None
                and MIN_EMPLOYEES <= company.employee_count <= MAX_EMPLOYEES,
                f"Required {MIN_EMPLOYEES}-{MAX_EMPLOYEES}; got {company.employee_count}",
            ),
            RuleCheck(
                "headcount_growth",
                company.headcount_growth_pct is not None
                and company.headcount_growth_pct >= MIN_HEADCOUNT_GROWTH_PCT,
                f"Required {MIN_HEADCOUNT_GROWTH_PCT}%+; got {company.headcount_growth_pct}",
            ),
            RuleCheck(
                "company_type",
                company.company_type in ALLOWED_COMPANY_TYPES,
                f"Required private/public/venture-backed; got {company.company_type}",
            ),
            RuleCheck(
                "hiring",
                company.is_hiring is True,
                f"Required hiring=yes; got {company.is_hiring}",
            ),
            RuleCheck(
                "industry",
                company.industry in PRIORITY_INDUSTRIES,
                f"Required priority industry; got {company.industry}",
            ),
            RuleCheck(
                "geography",
                company.geography in TARGET_GEOGRAPHIES,
                f"Required target geography; got {company.geography}",
            ),
        )
        return ICPEvaluation(matches=all(item.passed for item in checks), checks=checks)

    def evaluate_decision_maker(
        self,
        person: Person,
        *,
        company_employee_count: int | None,
    ) -> ICPEvaluation:
        function_ok = person.function in ALLOWED_FUNCTIONS
        if person.seniority in CORE_SENIORITY:
            seniority_ok = True
            seniority_detail = f"{person.seniority} is an allowed seniority"
        elif person.seniority is Seniority.MANAGER:
            seniority_ok = (
                company_employee_count is not None
                and company_employee_count < MANAGER_ALLOWED_BELOW_EMPLOYEES
            )
            seniority_detail = (
                "Managers only for companies under 200 employees; "
                f"company size={company_employee_count}"
            )
        else:
            seniority_ok = False
            seniority_detail = f"Seniority {person.seniority} is not in the SOP list"
        checks = (
            RuleCheck("function", function_ok, f"Function={person.function}"),
            RuleCheck("seniority", seniority_ok, seniority_detail),
        )
        return ICPEvaluation(matches=all(item.passed for item in checks), checks=checks)


DEFAULT_ICP_RULESET = ICPRuleset()
