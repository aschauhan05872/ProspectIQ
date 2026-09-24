"""Structured logging with request/job/tenant fields. Never log secrets."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

_SECRET_KEYS = {
    "password",
    "secret",
    "api_key",
    "apikey",
    "token",
    "authorization",
    "cookie",
    "client_secret",
    "access_token",
    "refresh_token",
}


def _redact(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in _SECRET_KEYS or key.lower().endswith("_key") or key.lower().endswith(
            "_secret"
        ):
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
