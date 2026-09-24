"""Intermark Global Phase 4 research evidence fixtures (no network)."""

from __future__ import annotations

from uuid import UUID

from prospectiq.domain.common import CompanyId, EvidenceId
from prospectiq.domain.company_facts import EvidencePageContext

CASE_ID = UUID("99a5e717-a0e3-4f9c-88b3-cf540f1e53fb")
COMPANY_ID = CompanyId(UUID("7f75ae69-2f97-44cd-baf1-8473fda8e21c"))


def intermark_evidence_contexts() -> list[EvidencePageContext]:
    return [
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("944ad75d-46ed-43b9-8602-85ece8e9a778")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/",
            page_type="home",
            title="Real estate for investment and immigration | Intermark Global",
            text=(
                "INTERMARK GLOBAL. Real Estate for life, investments and immigration\n"
                "More than 1000+ real estate options for investment\n"
                "Investment\nImmigration\nPurchase of property\n"
                "With 7 offices, over 500 partner globally we serve clients worldwide."
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "home"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("4b0a0604-d09c-4457-acc1-cc3636f4220c")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/about",
            page_type="about",
            title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
            text=(
                "About company\nOur mission\nOur services\n"
                "Intermark Global – Real estate for living, investment and immigration\n"
                "Our mission A future focused real estate advisory."
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "about"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("fcd320f0-87c1-411c-aafa-8492753dc389")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/contacts",
            page_type="contact",
            title="Contact Intermark Global | Our Offices Worldwide",
            text=(
                "Contact us\nOffice entry rules\n"
                "Email client@intermark.global Phone +9714 439 6368\n"
                "Submit your details through our website or contact form to request consultation.\n"
                "Offices United Kingdom London Indonesia Bali China Shanghai "
                "United Arab Emirates Dubai Thailand Phuket Turkey Istanbul"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "contact"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("c00347c2-fb0a-402e-b9e9-79d276d176e4")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/events",
            page_type="other",
            title="Intermark Global Events | Real Estate & Investment Webinars",
            text=(
                "Events\n"
                "Intermark Global Holds Exclusive Real Estate Events in Phuket for Top Agents\n"
                "Check out the most important events\nAll events"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("acedef28-ebec-4e55-8c2d-a03946c479f6")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/events/1",
            page_type="other",
            title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
            text=(
                "Financial breakthrough: The path to smart investments\n"
                "About event\nWhat will we discuss on the forum\n"
                "The program of the event"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("f174130d-a0f6-4bc2-bbfb-2638dc0a7f4f")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/events/2",
            page_type="other",
            title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
            text=(
                "Financial breakthrough: The path to smart investments2\n"
                "The experts' knowledge is packed in one place"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("daa0e40a-7aad-4e34-80b7-aa0170a34f40")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/events/3",
            page_type="other",
            title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
            text=(
                "Intermark Global Holds Exclusive Real Estate Events in Phuket\n"
                "About event\nThe program of the event"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("0302856d-a0bd-492b-93ae-ad6c96d12c45")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/events/4",
            page_type="other",
            title="May",
            text=(
                "Intermark Global at IMI Online completed\n"
                "About event\nThe program of the event"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("2b729a01-03e5-43fb-a18c-26f07a6faf31")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/events/5",
            page_type="other",
            title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
            text=(
                "Intermark Global at IMI Offline completed\n"
                "About event\nThe program of the event"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
        EvidencePageContext(
            evidence_id=EvidenceId(UUID("948924f1-d43c-490e-9a3b-0f9524c8ed64")),
            company_id=COMPANY_ID,
            source_locator="https://intermark.global/expert-blog",
            page_type="other",
            title="Intermark Global Expert Blog | Investment & Immigration News",
            text=(
                "Blog\nAll materials\n"
                "Where to invest in 2027? Top 3 real estate markets Bali, Phuket or Dubai\n"
                "Blog September 16, 2026"
            ),
            metadata={"research_case_id": str(CASE_ID), "page_type": "other"},
        ),
    ]
