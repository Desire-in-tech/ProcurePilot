import json

import httpx
import pytest

from app.ai.providers.anakin import AnakinProvider


def make_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_sends_correct_anakin_request():
    captured = {}

    async def handler(request: httpx.Request):
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = request.content

        return httpx.Response(
            200,
            json={
                "id": "search-123",
                "results": [
                    {
                        "url": "https://supplier.example.com/laptops",
                        "title": "Business Laptops",
                        "snippet": "Business laptops with 16GB RAM.",
                        "date": "2026-09-11",
                    }
                ],
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        results = await provider.search(
            "Find business laptops",
            max_results=5,
        )
    finally:
        httpx.AsyncClient = original_client

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.anakin.io/v1/search"
    assert captured["headers"]["x-api-key"] == "test-key"

    assert results[0].title == "Business Laptops"
    assert results[0].url == "https://supplier.example.com/laptops"
    assert results[0].snippet == "Business laptops with 16GB RAM."
    assert results[0].metadata["date"] == "2026-09-11"


@pytest.mark.asyncio
async def test_agentic_search_returns_job():
    async def handler(request: httpx.Request):
        assert request.method == "POST"
        assert str(request.url) == (
            "https://api.anakin.io/v1/agentic-search"
        )

        return httpx.Response(
            202,
            json={
                "job_id": "agentic-123",
                "status": "pending",
                "message": "Research job created",
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        job = await provider.agentic_search(
            "Find reputable laptop suppliers"
        )
    finally:
        httpx.AsyncClient = original_client

    assert job.external_job_id == "agentic-123"
    assert job.status == "pending"
    assert job.metadata["message"] == "Research job created"


@pytest.mark.asyncio
async def test_get_agentic_job_returns_completed_result():
    async def handler(request: httpx.Request):
        assert request.method == "GET"
        assert str(request.url) == (
            "https://api.anakin.io/v1/agentic-search/agentic-123"
        )

        return httpx.Response(
            200,
            json={
                "id": "agentic-123",
                "status": "completed",
                "jobType": "agentic_search",
                "generatedJson": {
                    "summary": "Three suppliers found.",
                    "structured_data": {
                        "suppliers": 3,
                    },
                },
                "durationMs": 4200,
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        job = await provider.get_job("agentic-123")
    finally:
        httpx.AsyncClient = original_client

    assert job.external_job_id == "agentic-123"
    assert job.status == "completed"
    assert job.result["summary"] == "Three suppliers found."
    assert job.result["structured_data"]["suppliers"] == 3


@pytest.mark.asyncio
async def test_scrape_submits_url_scraper_job_with_output_schema():
    schema = {
        "type": "object",
        "properties": {
            "supplier_name": {"type": "string"},
            "price": {"type": ["number", "null"]},
        },
    }

    async def handler(request: httpx.Request):
        assert request.method == "POST"
        assert str(request.url) == (
            "https://api.anakin.io/v1/url-scraper"
        )

        payload = json.loads(request.content)

        assert payload["url"] == (
            "https://supplier.example.com/product"
        )
        assert payload["useBrowser"] is True
        assert payload["generateJson"] is True
        assert payload["outputSchema"] == schema
        assert "jsonSchema" not in payload

        return httpx.Response(
            202,
            json={
                "jobId": "scrape-123",
                "status": "pending",
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        result = await provider.scrape(
            "https://supplier.example.com/product",
            schema=schema,
            use_browser=True,
        )
    finally:
        httpx.AsyncClient = original_client

    assert result.url == "https://supplier.example.com/product"
    assert result.metadata["job_id"] == "scrape-123"
    assert result.metadata["status"] == "pending"
    assert result.metadata["job_type"] == "url_scraper"


@pytest.mark.asyncio
async def test_get_scrape_job_returns_scraped_content():
    async def handler(request: httpx.Request):
        assert request.method == "GET"
        assert str(request.url) == (
            "https://api.anakin.io/v1/url-scraper/scrape-123"
        )

        return httpx.Response(
            200,
            json={
                "id": "scrape-123",
                "status": "completed",
                "url": "https://supplier.example.com/product",
                "title": "Business Laptop Pro",
                "markdown": "# Business Laptop Pro\n\n16GB RAM.",
                "generatedJson": {
                    "price": 1180,
                    "currency": "EUR",
                },
                "durationMs": 2100,
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        result = await provider.get_scrape_job("scrape-123")
    finally:
        httpx.AsyncClient = original_client

    assert result.url == "https://supplier.example.com/product"
    assert result.title == "Business Laptop Pro"
    assert result.content == "# Business Laptop Pro\n\n16GB RAM."
    assert result.structured_data["price"] == 1180
    assert result.structured_data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_get_scrape_job_preserves_structured_generated_json():
    expected = {
        "supplier_name": "Nordic Tech Supply",
        "product_name": "Business Laptop Pro 14",
        "price": 1180,
        "currency": "EUR",
    }

    async def handler(request: httpx.Request):
        assert request.method == "GET"
        assert str(request.url) == (
            "https://api.anakin.io/v1/url-scraper/scrape-structured"
        )

        return httpx.Response(
            200,
            json={
                "id": "scrape-structured",
                "status": "completed",
                "url": "https://supplier.example.com/product",
                "title": "Business Laptop Pro 14",
                "markdown": "# Business Laptop Pro 14",
                "generatedJson": expected,
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        result = await provider.get_scrape_job("scrape-structured")
    finally:
        httpx.AsyncClient = original_client

    assert result.structured_data == expected
    assert result.structured_data["supplier_name"] == (
        "Nordic Tech Supply"
    )
    assert result.structured_data["price"] == 1180


@pytest.mark.asyncio
async def test_batch_scrape_submits_maximum_allowed_urls():
    urls = [
        f"https://supplier.example.com/product-{index}"
        for index in range(1, 11)
    ]

    async def handler(request: httpx.Request):
        assert request.method == "POST"
        assert str(request.url) == (
            "https://api.anakin.io/v1/url-scraper/batch"
        )

        return httpx.Response(
            202,
            json={
                "jobId": "batch-123",
                "status": "pending",
            },
        )

    provider = AnakinProvider("test-key")

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = make_transport(handler)
        return original_client(*args, **kwargs)

    httpx.AsyncClient = client_factory

    try:
        results = await provider.batch_scrape(urls)
    finally:
        httpx.AsyncClient = original_client

    assert len(results) == 10
    assert all(
        result.metadata["job_id"] == "batch-123"
        for result in results
    )


@pytest.mark.asyncio
async def test_search_rejects_empty_query():
    provider = AnakinProvider("test-key")

    with pytest.raises(ValueError, match="Search query cannot be empty"):
        await provider.search("")


@pytest.mark.asyncio
async def test_search_rejects_invalid_result_limit():
    provider = AnakinProvider("test-key")

    with pytest.raises(
        ValueError,
        match="max_results must be between 1 and 20",
    ):
        await provider.search("laptops", max_results=21)
