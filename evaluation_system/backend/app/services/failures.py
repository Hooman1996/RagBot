"""Content-free semantic versus infrastructure failure classification."""

from __future__ import annotations

import asyncio

from utils.service_errors import InvalidRequestError, ServiceError

try:
    from sqlalchemy.exc import SQLAlchemyError
except ImportError:  # Lets dependency checks/unit tests run before installation.
    class SQLAlchemyError(Exception):
        pass


def is_infrastructure_error(exc: Exception) -> bool:
    if isinstance(exc, InvalidRequestError):
        return False
    return isinstance(
        exc,
        (
            ServiceError,
            SQLAlchemyError,
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    )
