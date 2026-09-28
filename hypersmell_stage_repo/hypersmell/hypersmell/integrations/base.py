import abc
import time
from dataclasses import dataclass
from functools import wraps

import httpx
from loguru import logger


def retry(max_retries: int = 3, retry_on: tuple[type, ...] = (httpx.HTTPStatusError,)):
    """Retry decorator with exponential backoff.

    Handles 429 responses by respecting Retry-After header.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    last_exception = e
                    if e.response.status_code == 429:
                        retry_after = int(e.response.headers.get("Retry-After", 2))
                        logger.warning(
                            f"Rate limited, retrying after {retry_after}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(retry_after)
                    elif isinstance(e, retry_on):
                        wait = 2 ** attempt
                        logger.warning(
                            f"Request failed, retrying in {wait}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait)
                    else:
                        raise
                except retry_on as e:
                    last_exception = e
                    wait = 2 ** attempt
                    logger.warning(
                        f"Request failed, retrying in {wait}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
            raise last_exception
        return wrapper
    return decorator


@dataclass
class PaginatedResult:
    """Cursor-based pagination result."""
    items: list[dict]
    next_cursor: str | None


class Integration(abc.ABC):
    """Base class for all integrations.

    Subclasses must implement list_resources() and fetch_resource().
    """

    def __init__(self, connection, settings):
        self.connection = connection
        self.settings = settings
        self.client = httpx.Client(timeout=30)

    @abc.abstractmethod
    def list_resources(self, cursor: str | None = None) -> PaginatedResult:
        """List available resources from the external service."""
        ...

    @abc.abstractmethod
    def fetch_resource(self, external_id: str) -> dict:
        """Fetch a single resource's full content."""
        ...

    def list_all_resources(self) -> list[dict]:
        """Paginate through all resources."""
        all_items = []
        cursor = None
        while True:
            result = self.list_resources(cursor=cursor)
            all_items.extend(result.items)
            if not result.next_cursor:
                break
            cursor = result.next_cursor
        return all_items

    def close(self):
        self.client.close()
