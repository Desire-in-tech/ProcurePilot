from typing import Any

from app.ai.providers.base import (
    ResearchJob,
    ResearchProvider,
    ScrapeResult,
    SearchResult,
)


class AnakinProvider:
    """
    Adapter boundary for Anakin.

    The orchestration layer depends on this interface rather than
    Anakin-specific request/response formats.

    Real API operations will be implemented after the workflow
    and persistence contracts are tested.
    """

    name = "anakin"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Anakin API key is required")

        self.api_key = api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> list[SearchResult]:
        raise NotImplementedError(
            "Anakin Search API integration is not implemented yet"
        )

    async def agentic_search(
        self,
        query: str,
    ) -> ResearchJob:
        raise NotImplementedError(
            "Anakin Agentic Search integration is not implemented yet"
        )

    async def scrape(
        self,
        url: str,
        *,
        schema: dict[str, Any] | None = None,
        use_browser: bool = False,
    ) -> ScrapeResult:
        raise NotImplementedError(
            "Anakin URL Scraper integration is not implemented yet"
        )

    async def batch_scrape(
        self,
        urls: list[str],
        *,
        schema: dict[str, Any] | None = None,
    ) -> list[ScrapeResult]:
        raise NotImplementedError(
            "Anakin Batch Scraper integration is not implemented yet"
        )

    async def get_job(
        self,
        external_job_id: str,
    ) -> ResearchJob:
        raise NotImplementedError(
            "Anakin job polling integration is not implemented yet"
        )
