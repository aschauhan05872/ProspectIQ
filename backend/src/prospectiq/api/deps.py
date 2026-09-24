"""Request dependencies. V0 uses the internal tenant from configuration."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.domain.common import TenantId, TenantScope, UserId, WorkspaceId
from prospectiq.infrastructure.config import Settings, get_settings
from prospectiq.infrastructure.db import get_session_factory


def settings_dep() -> Settings:
    return get_settings()


def tenant_scope(settings: Settings = Depends(settings_dep)) -> TenantScope:
    return TenantScope(
        tenant_id=TenantId(settings.internal_tenant_id),
        workspace_id=WorkspaceId(settings.internal_workspace_id),
        user_id=UserId(settings.internal_user_id),
    )


async def db_session(
    request: Request,
    settings: Settings = Depends(settings_dep),
) -> AsyncIterator[AsyncSession]:
    factory = get_session_factory(settings)
    async with factory() as session:
        request.state.db_session = session
        yield session
        await session.commit()
