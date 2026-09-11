from typing import Any

from app.ai.providers.base import (
    ResearchJob,
    ScrapeResult,
    SearchResult,
)


class MockResearchProvider:
    name = "mock"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> list[SearchResult]:
        return [
            SearchResult(
                title="Mock Supplier Result",
                url="https://example.com/supplier",
                snippet=f"Mock result for: {query}",
            )
        ][:max_results]

    async def agentic_search(
        self,
        query: str,
    ) -> ResearchJob:
        return ResearchJob(
            external_job_id="mock-job-1",
            status="completed",
            result={
                "query": query,
                "sources": [],
            },
        )

    async def scrape(
        self,
        url: str,
        *,
        schema: dict[str, Any] | None = None,
        use_browser: bool = False,
    ) -> ScrapeResult:
        return ScrapeResult(
            url=url,
            title="Mock Source",
            content="Mock scraped content.",
            structured_data={},
        )

    async def batch_scrape(
        self,
        urls: list[str],
        *,
        schema: dict[str, Any] | None = None,
    ) -> list[ScrapeResult]:
        results = []

        for url in urls:
            results.append(
                await self.scrape(
                    url,
                    schema=schema,
                )
            )

        return results

    async def get_job(
        self,
        external_job_id: str,
    ) -> ResearchJob:
        return ResearchJob(
            external_job_id=external_job_id,
            status="completed",
            result={},
        )

    async def get_scrape_job(
        self,
        external_job_id: str,
    ) -> ScrapeResult:
        return ScrapeResult(
            url="https://example.com/supplier",
            title="Mock Source",
            content="Mock scraped content.",
            structured_data={},
            metadata={
                "job_id": external_job_id,
                "status": "completed",
            },
        )
