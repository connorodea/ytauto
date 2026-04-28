"""Retry decorator for transient API failures with exponential backoff."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# HTTP status codes that are retryable
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable(exc: Exception) -> bool:
    """Check if an exception is retryable."""
    # Direct match
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True

    # Anthropic errors
    try:
        import anthropic
        if isinstance(exc, (anthropic.InternalServerError, anthropic.RateLimitError,
                            anthropic.APIConnectionError, anthropic.APITimeoutError)):
            return True
    except ImportError:
        pass

    # OpenAI errors
    try:
        import openai
        if isinstance(exc, (openai.InternalServerError, openai.RateLimitError,
                            openai.APIConnectionError, openai.APITimeoutError)):
            return True
    except ImportError:
        pass

    # httpx errors (Deepgram, image downloads)
    try:
        import httpx
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in RETRYABLE_STATUS_CODES
    except ImportError:
        pass

    # Generic: check for status_code attribute
    status = getattr(exc, "status_code", None)
    if status and status in RETRYABLE_STATUS_CODES:
        return True

    return False


def retry(
    max_attempts: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
) -> Callable:
    """Decorator that retries a function on transient failures.

    Uses exponential backoff: delay = initial_delay * backoff_factor^attempt
    Only retries on errors identified as transient by is_retryable().

    Example:
        @retry(max_attempts=3)
        def call_api(): ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc

                    if not is_retryable(exc) or attempt == max_attempts:
                        raise

                    delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    logger.warning(
                        "Retry %d/%d for %s after %.1fs — %s: %s",
                        attempt, max_attempts, func.__name__, delay,
                        type(exc).__name__, str(exc)[:200],
                    )
                    time.sleep(delay)

            raise last_exc  # Should never reach here

        return wrapper
    return decorator
