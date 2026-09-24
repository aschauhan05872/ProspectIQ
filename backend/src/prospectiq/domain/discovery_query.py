"""Provider-neutral discovery query construction. No HTTP I/O."""

from __future__ import annotations

from prospectiq.domain.company import GEOGRAPHY_ALIASES, INDUSTRY_ALIASES, Geography, Industry
from prospectiq.domain.discovery import DiscoveryRequest


def _label_for_industry(industry: Industry) -> str:
    for label, value in INDUSTRY_ALIASES.items():
        if value is industry:
            return label.replace("/", " ")
    return industry.value.replace("_", " ")


def _label_for_geography(geography: Geography) -> str:
    for label, value in GEOGRAPHY_ALIASES.items():
        if value is geography:
            return label
    return geography.value.replace("_", " ")


def build_discovery_query(request: DiscoveryRequest) -> str:
    parts = [_label_for_industry(request.industry), "companies"]
    if request.countries:
        parts.append("in")
        parts.append(", ".join(_label_for_geography(item) for item in request.countries))
    if request.hiring_required:
        parts.append("hiring")
    if request.employee_min or request.employee_max:
        parts.append(f"{request.employee_min}-{request.employee_max} employees")
    if request.keywords:
        parts.extend(request.keywords)
    return " ".join(parts)
