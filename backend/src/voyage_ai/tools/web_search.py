import os
import logging
import time

import requests
from tavily.errors import (
    BadRequestError,
    ForbiddenError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    TimeoutError as TavilyTimeoutError,
    UsageLimitExceededError,
)

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()

logger = logging.getLogger(__name__)
DESTINATION_SEARCH_TIMEOUT_SECONDS = 20
DESTINATION_SEARCH_MAX_ATTEMPTS = 2
DESTINATION_SEARCH_RETRY_DELAY_SECONDS = 0.5


class DestinationResearchProviderError(RuntimeError):
    """Safe wrapper for an unrecoverable destination-search provider failure."""


_TRANSIENT_SEARCH_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    TavilyTimeoutError,
)
_PROVIDER_SEARCH_ERRORS = (
    BadRequestError,
    ForbiddenError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    UsageLimitExceededError,
)


client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


def search_destination(
    destination: str,
    interests: list[str],
    max_results: int = 6,
) -> list[dict]:
    """
    Search the web for destination information
    relevant to the user's interests.
    """

    if interests:
        interest_text = ", ".join(interests)
    else:
        interest_text = "top attractions and travel experiences"

    query = (
        f"{destination} travel guide best places "
        f"for {interest_text}"
    )

    response = _search_destination_with_retry(query, max_results)

    sources = []

    for index, result in enumerate(
        response["results"],
        start=1,
    ):
        sources.append(
            {
                "id": index,
                "title": result["title"],
                "url": result["url"],
                "content": result["content"],
            }
        )

    return sources


def _search_destination_with_retry(query: str, max_results: int) -> dict:
    """Retry only safe-to-repeat transient Tavily searches, at most once."""
    for attempt in range(DESTINATION_SEARCH_MAX_ATTEMPTS):
        try:
            return client.search(
                query=query,
                search_depth="basic",
                max_results=max_results,
                timeout=DESTINATION_SEARCH_TIMEOUT_SECONDS,
            )
        except _TRANSIENT_SEARCH_ERRORS as error:
            if attempt + 1 >= DESTINATION_SEARCH_MAX_ATTEMPTS:
                logger.warning(
                    "Tavily destination search exhausted bounded retries "
                    "(attempts=%d exception_type=%s)",
                    attempt + 1,
                    type(error).__name__,
                )
                raise DestinationResearchProviderError(
                    "Destination research provider is temporarily unavailable."
                ) from error
            delay = min(DESTINATION_SEARCH_RETRY_DELAY_SECONDS * (2 ** attempt), 1.0)
            logger.warning(
                "Tavily destination search encountered transient failure; retrying "
                "(attempt=%d exception_type=%s delay_seconds=%.1f)",
                attempt + 1,
                type(error).__name__,
                delay,
            )
            time.sleep(delay)
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else None
            if status_code is not None and status_code >= 500 and attempt + 1 < DESTINATION_SEARCH_MAX_ATTEMPTS:
                delay = min(DESTINATION_SEARCH_RETRY_DELAY_SECONDS * (2 ** attempt), 1.0)
                logger.warning(
                    "Tavily destination search returned a temporary server error; retrying "
                    "(attempt=%d status_code=%d delay_seconds=%.1f)",
                    attempt + 1,
                    status_code,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.warning(
                "Tavily destination search failed with HTTP response "
                "(status_code=%s)",
                status_code if status_code is not None else "unknown",
            )
            raise DestinationResearchProviderError(
                "Destination research is unavailable from the configured provider."
            ) from error
        except _PROVIDER_SEARCH_ERRORS as error:
            # Authentication, request, permission, and quota errors are not
            # transient connection failures and must not be retried blindly.
            logger.warning(
                "Tavily destination search rejected request "
                "(exception_type=%s)",
                type(error).__name__,
            )
            raise DestinationResearchProviderError(
                "Destination research is unavailable from the configured provider."
            ) from error

    raise AssertionError("unreachable retry loop exit")


def search_trip_costs(query: str, max_results: int = 3) -> list[dict]:
    """Search Tavily for category-targeted evidence and page text when available."""
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content="text",
    )
    return [
        {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "content": result.get("content", ""),
            "raw_content": result.get("raw_content", ""),
        }
        for result in response.get("results", [])
    ]
