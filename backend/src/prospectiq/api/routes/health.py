from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, settings_dep
from prospectiq.infrastructure.config import Settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    settings: Settings = Depends(settings_dep),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready", "env": settings.env}
