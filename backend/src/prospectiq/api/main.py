"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prospectiq.api.routes.companies import companies_router, research_cases_router
from prospectiq.api.routes.discovery import router as discovery_router
from prospectiq.api.routes.health import router as health_router
from prospectiq.api.routes.operator import operator_router
from prospectiq.api.routes.prospects import router as prospects_router
from prospectiq.api.routes.resources import (
    activities_router,
    drafts_router,
    followups_router,
    leads_router,
    notifications_router,
    research_router,
    searches_router,
)
from prospectiq.api.routes.sources import router as sources_router
from prospectiq.infrastructure.config import get_settings
from prospectiq.infrastructure.db import dispose_engine
from prospectiq.infrastructure.logging import configure_logging, get_logger

logger = get_logger("prospectiq.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("api_starting", env=settings.env)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="ProspectIQ",
        description="AI Lead Intelligence Engine — internal V0 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(searches_router)
    application.include_router(leads_router)
    application.include_router(research_router)
    application.include_router(drafts_router)
    application.include_router(activities_router)
    application.include_router(followups_router)
    application.include_router(notifications_router)
    application.include_router(sources_router)
    application.include_router(prospects_router)
    application.include_router(companies_router)
    application.include_router(research_cases_router)
    application.include_router(discovery_router)
    application.include_router(operator_router)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "prospectiq.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.env == "development",
    )
