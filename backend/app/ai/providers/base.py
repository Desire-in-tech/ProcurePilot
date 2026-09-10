from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    url: str
    title: str | None = None
    content: str | None = None
    structured_data: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchJob:
    external_job_id: str
    status: str
    result: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchSourceResult:
    url: str
    title: str | None
    content: str | None
    source_type: str
    provider: str
    external_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ResearchProvider(Protocol):
    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> list[SearchResult]:
        ...

    async def agentic_search(
        self,
        query: str,
    ) -> ResearchJob:
        ...

    async def scrape(
        self,
        url: str,
        *,
        schema: dict[str, Any] | None = None,
        use_browser: bool = False,
    ) -> ScrapeResult:
        ...

    async def batch_scrape(
        self,
        urls: list[str],
        *,
        schema: dict[str, Any] | None = None,
    ) -> list[ScrapeResult]:
        ...

    async def get_job(
        self,
        external_job_id: str,
    ) -> ResearchJob:
        ...
