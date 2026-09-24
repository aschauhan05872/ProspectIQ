"""Notification adapters. V0 logs only; email/Telegram come later."""

from __future__ import annotations

from typing import Any

from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.notifications")


class LoggingNotificationAdapter:
    async def send(self, channel: str, title: str, body: str, payload: dict[str, Any]) -> None:
        logger.info(
            "notification_logged",
            channel=channel,
            title=title,
            body=body,
            payload_keys=sorted(payload),
        )
