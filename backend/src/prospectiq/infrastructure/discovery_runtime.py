"""Compose company discovery from configured provider and existing ingestion."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.discovery import CompanyDiscoveryService
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.discovery.provider_factory import build_discovery_provider
from prospectiq.infrastructure.ingestion_runtime import build_ingestion_service
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.repositories import (
    SqlAlchemyDiscoveryCandidateRepository,
    SqlAlchemyEvidenceRepository,
)


def build_discovery_service(
    session: AsyncSession,
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> CompanyDiscoveryService:
    return CompanyDiscoveryService(
        jobs=PostgresJobQueue(session),
        candidates=SqlAlchemyDiscoveryCandidateRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        ingestion=build_ingestion_service(session, settings),
        provider=build_discovery_provider(settings, client=client),
    )
