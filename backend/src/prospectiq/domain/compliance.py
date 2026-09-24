"""LinkedIn and unauthorized-automation boundary.

ProspectIQ does not automate unauthorized LinkedIn activity. This module is the
architectural enforcement point: adapters, jobs, and AI tools must pass these
checks before they can be registered or executed.
"""

from __future__ import annotations

from enum import StrEnum


class HumanControlledAction(StrEnum):
    OPEN_LINKEDIN = "open_linkedin"
    VERIFY_PERSON_OR_COMPANY = "verify_person_or_company"
    SEND_CONNECTION_REQUEST = "send_connection_request"
    SEND_LINKEDIN_MESSAGE = "send_linkedin_message"
    READ_OR_RESPOND_TO_CONVERSATION = "read_or_respond_to_conversation"
    DECIDE_WHETHER_TO_PURSUE = "decide_whether_to_pursue"


class AutomatedCapability(StrEnum):
    COMPANY_DISCOVERY = "company_discovery"
    PERMITTED_PUBLIC_DATA_COLLECTION = "permitted_public_data_collection"
    COMPANY_RESEARCH = "company_research"
    MARKET_SIGNAL_DETECTION = "market_signal_detection"
    DATA_AGGREGATION = "data_aggregation"
    ENRICHMENT = "enrichment"
    LEAD_QUALIFICATION = "lead_qualification"
    DETERMINISTIC_SCORING = "deterministic_scoring"
    AI_RESEARCH_SUMMARY = "ai_research_summary"
    OUTREACH_DRAFTING = "outreach_drafting"
    NOTIFICATIONS = "notifications"
    FOLLOW_UP_SCHEDULING = "follow_up_scheduling"
    CRM_LEAD_TRACKING = "crm_lead_tracking"
    ANALYTICS = "analytics"


class ForbiddenCapability(StrEnum):
    LINKEDIN_SCRAPING = "linkedin_scraping"
    LINKEDIN_BROWSER_AUTOMATION = "linkedin_browser_automation"
    CREDENTIAL_BASED_LINKEDIN_AUTOMATION = "credential_based_linkedin_automation"
    AUTOMATED_CONNECTION_SENDING = "automated_connection_sending"
    AUTOMATED_LINKEDIN_MESSAGE_SENDING = "automated_linkedin_message_sending"
    ANTI_DETECTION = "anti_detection"
    RATE_LIMIT_BYPASS = "rate_limit_bypass"
    CAPTCHA_BYPASS = "captcha_bypass"
    SESSION_HIJACKING = "session_hijacking"
    CIRCUMVENT_LINKEDIN_RESTRICTIONS = "circumvent_linkedin_restrictions"


class LinkedInComplianceError(Exception):
    """Raised when code attempts a forbidden or unauthorized LinkedIn capability."""


_FORBIDDEN_MARKERS = {
    "linkedin_scrape",
    "linkedin_scraping",
    "browser_automation",
    "playwright_linkedin",
    "selenium_linkedin",
    "linkedin_session",
    "linkedin_cookie",
    "auto_connect",
    "auto_message",
    "anti_detect",
    "undetected_chromedriver",
    "captcha_bypass",
    "rate_limit_bypass",
    "session_hijack",
}


def assert_capability_allowed(
    *,
    adapter_key: str,
    uses_linkedin_credentials: bool = False,
    automates_linkedin_engagement: bool = False,
    official_linkedin_authorized: bool = False,
    claims_official_linkedin: bool = False,
) -> None:
    """Reject forbidden LinkedIn automation at registration/execution time."""

    key = adapter_key.lower().replace("-", "_")
    for marker in _FORBIDDEN_MARKERS:
        if marker in key:
            raise LinkedInComplianceError(
                f"Adapter '{adapter_key}' is forbidden: matches '{marker}'. "
                "ProspectIQ does not scrape LinkedIn or automate engagement."
            )

    if uses_linkedin_credentials and not official_linkedin_authorized:
        raise LinkedInComplianceError(
            "Credential-based LinkedIn access is forbidden unless an official "
            "authorized integration is enabled."
        )

    if automates_linkedin_engagement:
        raise LinkedInComplianceError(
            "Automated LinkedIn connection or messaging is forbidden. "
            "Those actions are human-controlled."
        )

    if claims_official_linkedin and not official_linkedin_authorized:
        raise LinkedInComplianceError(
            "Official LinkedIn adapter is disabled until an authorized integration "
            "is configured."
        )
