from typing import Any

import httpx

from app.ai.providers.base import (
    ResearchJob,
    ScrapeResult,
    SearchResult,
)


class AnakinProvider:
    """
    Adapter for Anakin.io research APIs used by ProcurePilot.

    Supported capabilities:
    - synchronous Search
    - asynchronous Agentic Search submission/polling
    - asynchronous URL scraping submission
    - asynchronous batch URL scraping submission

    All requests are sent to the official Anakin API:
    https://api.anakin.io/v1
    """

    name = "anakin"
    base_url = "https://api.anakin.io/v1"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("Anakin API key is required")

        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        """
        Execute Anakin's synchronous Search API.

        POST /v1/search
        """
        if not query.strip():
            raise ValueError("Search query cannot be empty")

        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20")

        payload = {
            "prompt": query,
            "limit": max_results,
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            response = await client.post("/search", json=payload)

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        results: list[SearchResult] = []

        for item in data.get("results", []):
            if not item.get("url"):
                continue

            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item["url"],
                    snippet=item.get("snippet"),
                    metadata={
                        key: value
                        for key, value in item.items()
                        if key not in {"title", "url", "snippet"}
                    },
                )
            )

        return results

    async def agentic_search(
        self,
        query: str,
    ) -> ResearchJob:
        """
        Submit an asynchronous Agentic Search job.

        POST /v1/agentic-search
        """
        if not query.strip():
            raise ValueError("Agentic search query cannot be empty")

        payload = {
            "prompt": query,
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/agentic-search",
                json=payload,
            )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        job_id = data.get("job_id") or data.get("id")

        if not job_id:
            raise ValueError(
                "Anakin Agentic Search response did not contain a job ID"
            )

        return ResearchJob(
            external_job_id=job_id,
            status=data.get("status", "pending"),
            metadata={
                key: value
                for key, value in data.items()
                if key not in {"job_id", "id", "status"}
            },
        )

    async def scrape(
        self,
        url: str,
        *,
        schema: dict[str, Any] | None = None,
        use_browser: bool = False,
    ) -> ScrapeResult:
        """
        Submit an asynchronous Anakin URL Scraper job.

        POST /v1/url-scraper

        The returned ScrapeResult contains the external job ID in
        metadata. The completed result can be retrieved through
        get_scrape_job().
        """
        if not url.strip():
            raise ValueError("URL cannot be empty")

        payload: dict[str, Any] = {
            "url": url,
            "useBrowser": use_browser,
        }

        if schema is not None:
            payload["generateJson"] = True
            payload["jsonSchema"] = schema

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/url-scraper",
                json=payload,
            )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        job_id = data.get("jobId") or data.get("job_id") or data.get("id")

        if not job_id:
            raise ValueError(
                "Anakin URL Scraper response did not contain a job ID"
            )

        return ScrapeResult(
            url=url,
            metadata={
                "job_id": job_id,
                "status": data.get("status", "pending"),
                "job_type": "url_scraper",
            },
        )

    async def batch_scrape(
        self,
        urls: list[str],
        *,
        schema: dict[str, Any] | None = None,
    ) -> list[ScrapeResult]:
        """
        Submit an asynchronous batch URL scraping job.

        POST /v1/url-scraper/batch

        Anakin currently accepts up to 10 URLs per batch.
        """
        if not urls:
            raise ValueError("At least one URL is required")

        if len(urls) > 10:
            raise ValueError("Anakin batch scraping supports at most 10 URLs")

        cleaned_urls = [url.strip() for url in urls]

        if any(not url for url in cleaned_urls):
            raise ValueError("URLs cannot be empty")

        payload: dict[str, Any] = {
            "urls": cleaned_urls,
        }

        if schema is not None:
            payload["generateJson"] = True
            payload["jsonSchema"] = schema

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/url-scraper/batch",
                json=payload,
            )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        job_id = data.get("jobId") or data.get("job_id") or data.get("id")

        if not job_id:
            raise ValueError(
                "Anakin batch scraper response did not contain a job ID"
            )

        status = data.get("status", "pending")

        return [
            ScrapeResult(
                url=url,
                metadata={
                    "job_id": job_id,
                    "status": status,
                    "job_type": "url_scraper_batch",
                },
            )
            for url in cleaned_urls
        ]

    async def get_job(
        self,
        external_job_id: str,
    ) -> ResearchJob:
        """
        Poll an Agentic Search job.

        GET /v1/agentic-search/{id}
        """
        if not external_job_id.strip():
            raise ValueError("External job ID cannot be empty")

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            response = await client.get(
                f"/agentic-search/{external_job_id}",
            )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        result = data.get("generatedJson")

        return ResearchJob(
            external_job_id=external_job_id,
            status=data.get("status", "unknown"),
            result=result,
            metadata={
                key: value
                for key, value in data.items()
                if key not in {
                    "id",
                    "status",
                    "generatedJson",
                }
            },
        )

    async def get_scrape_job(
        self,
        external_job_id: str,
    ) -> ScrapeResult:
        """
        Poll an Anakin URL Scraper job.

        GET /v1/url-scraper/{id}
        """
        if not external_job_id.strip():
            raise ValueError("External job ID cannot be empty")

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            response = await client.get(
                f"/url-scraper/{external_job_id}",
            )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        generated_json = data.get("generatedJson")

        return ScrapeResult(
            url=data.get("url", ""),
            title=data.get("title"),
            content=data.get("markdown") or data.get("cleanedHtml"),
            structured_data=generated_json,
            metadata={
                key: value
                for key, value in data.items()
                if key not in {
                    "url",
                    "title",
                    "markdown",
                    "cleanedHtml",
                    "generatedJson",
                }
            },
        )
