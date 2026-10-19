import asyncio
import json

import httpx
import pytest

from app.ai.research_agent import (
    MAX_MODEL_TURNS,
    OPENROUTER_API_URL,
    OpenRouterResearchAgent,
    ResearchAgentError,
)


def tool_call(name, arguments, call_id="call-1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def completion(*tool_calls):
    message = {"role": "assistant"}
    if tool_calls:
        message["tool_calls"] = list(tool_calls)
    return {"choices": [{"message": message}]}


def install_openrouter_mock(monkeypatch, responses):
    requests = []
    original_client = httpx.AsyncClient
    response_items = list(responses)

    async def handler(request):
        requests.append(json.loads(request.content))
        item = response_items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    return requests


def response(payload, status_code=200):
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", OPENROUTER_API_URL),
        json=payload,
    )


def test_agent_executes_tools_feeds_results_back_and_finishes(monkeypatch):
    source_url = "https://supplier.example/laptops"
    requests = install_openrouter_mock(
        monkeypatch,
        [
            response(
                completion(
                    tool_call("search_suppliers", {"query": "business laptops"})
                )
            ),
            response(
                completion(
                    tool_call("scrape_source", {"url": source_url}, "call-2")
                )
            ),
            response(completion()),
        ],
    )
    searched = []
    scraped = []

    async def search(query):
        searched.append(query)
        return [{"url": source_url, "title": "Supplier", "snippet": "Found"}]

    async def scrape(url):
        scraped.append(url)
        return {"url": url, "title": "Supplier", "content": "Current price: 100"}

    asyncio.run(
        OpenRouterResearchAgent("secret", "test-model").research(
            "Find laptop suppliers",
            search_suppliers=search,
            scrape_source=scrape,
        )
    )

    assert searched == ["business laptops"]
    assert scraped == [source_url]
    search_feedback = json.loads(requests[1]["messages"][-1]["content"])
    assert search_feedback["sources"][0]["url"] == source_url
    scrape_feedback = json.loads(requests[2]["messages"][-1]["content"])
    assert scrape_feedback["content"] == "Current price: 100"
    assert all(request["model"] == "test-model" for request in requests)


def test_agent_requires_search_before_finish(monkeypatch):
    install_openrouter_mock(monkeypatch, [response(completion())])

    async def unused(_):
        raise AssertionError("action should not run")

    with pytest.raises(ResearchAgentError, match="finished without searching"):
        asyncio.run(
            OpenRouterResearchAgent("secret", "test-model").research(
                "Find suppliers",
                search_suppliers=unused,
                scrape_source=unused,
            )
        )


def test_agent_stops_at_model_turn_limit(monkeypatch):
    payloads = [
        completion(
            tool_call("search_suppliers", {"query": "laptops"}, f"call-{index}")
        )
        for index in range(MAX_MODEL_TURNS)
    ]
    requests = install_openrouter_mock(
        monkeypatch,
        [response(payload) for payload in payloads],
    )
    searches = []

    async def search(query):
        searches.append(query)
        return []

    async def unused(_):
        raise AssertionError("scrape should not run")

    asyncio.run(
        OpenRouterResearchAgent("secret", "test-model").research(
            "Find suppliers",
            search_suppliers=search,
            scrape_source=unused,
        )
    )

    assert len(requests) == MAX_MODEL_TURNS
    assert searches == ["laptops"]


def test_agent_stops_at_research_action_limit(monkeypatch):
    monkeypatch.setattr(
        "app.ai.research_agent.MAX_RESEARCH_ACTIONS",
        2,
    )
    urls = [f"https://supplier.example/{index}" for index in range(2)]
    payloads = [
        completion(tool_call("search_suppliers", {"query": "laptops"}))
    ]
    payloads.extend(
        completion(tool_call("scrape_source", {"url": url}, f"call-{index}"))
        for index, url in enumerate(urls, start=2)
    )
    requests = install_openrouter_mock(
        monkeypatch,
        [response(payload) for payload in payloads],
    )
    scraped = []

    async def search(_):
        return [{"url": url, "title": "Supplier"} for url in urls[:3]]

    async def scrape(url):
        scraped.append(url)
        return {"url": url, "content": "Supplier page"}

    asyncio.run(
        OpenRouterResearchAgent("secret", "test-model").research(
            "Find suppliers",
            search_suppliers=search,
            scrape_source=scrape,
        )
    )

    assert len(requests) == 3
    assert len(scraped) == 1


def test_agent_rejects_malformed_tool_arguments_and_continues(monkeypatch):
    malformed_call = {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "search_suppliers",
            "arguments": "{not-json",
        },
    }
    requests = install_openrouter_mock(
        monkeypatch,
        [
            response(completion(malformed_call)),
            response(
                completion(tool_call("search_suppliers", {"query": "laptops"}))
            ),
            response(completion()),
        ],
    )
    searches = []

    async def search(query):
        searches.append(query)
        return []

    async def unused(_):
        raise AssertionError("scrape should not run")

    asyncio.run(
        OpenRouterResearchAgent("secret", "test-model").research(
            "Find suppliers",
            search_suppliers=search,
            scrape_source=unused,
        )
    )

    assert searches == ["laptops"]
    feedback = json.loads(requests[1]["messages"][-1]["content"])
    assert feedback["error"] == "Tool arguments must be a JSON object."


def test_agent_rejects_scraping_urls_not_returned_by_search(monkeypatch):
    requests = install_openrouter_mock(
        monkeypatch,
        [
            response(
                completion(tool_call("search_suppliers", {"query": "laptops"}))
            ),
            response(
                completion(
                    tool_call(
                        "scrape_source",
                        {"url": "https://unlisted.example/"},
                        "call-2",
                    )
                )
            ),
            response(completion()),
        ],
    )

    async def search(_):
        return [{"url": "https://supplier.example/", "title": "Supplier"}]

    async def scrape(_):
        raise AssertionError("unlisted URL must not be scraped")

    asyncio.run(
        OpenRouterResearchAgent("secret", "test-model").research(
            "Find suppliers",
            search_suppliers=search,
            scrape_source=scrape,
        )
    )

    feedback = json.loads(requests[2]["messages"][-1]["content"])
    assert "exactly match" in feedback["error"]


def test_agent_handles_malformed_response(monkeypatch):
    malformed = httpx.Response(
        200,
        request=httpx.Request("POST", OPENROUTER_API_URL),
        content=b"not-json",
    )
    install_openrouter_mock(monkeypatch, [malformed])

    async def unused(_):
        raise AssertionError("action should not run")

    with pytest.raises(ResearchAgentError, match="malformed JSON"):
        asyncio.run(
            OpenRouterResearchAgent("secret", "test-model").research(
                "Find suppliers",
                search_suppliers=unused,
                scrape_source=unused,
            )
        )


def test_agent_sanitizes_openrouter_api_errors(monkeypatch):
    install_openrouter_mock(
        monkeypatch,
        [response({"error": {"message": "secret"}}, status_code=429)],
    )

    async def unused(_):
        raise AssertionError("action should not run")

    with pytest.raises(ResearchAgentError, match="HTTP 429") as error:
        asyncio.run(
            OpenRouterResearchAgent("secret", "test-model").research(
                "Find suppliers",
                search_suppliers=unused,
                scrape_source=unused,
            )
        )
    assert "secret" not in str(error.value)


def test_agent_propagates_provider_errors(monkeypatch):
    install_openrouter_mock(
        monkeypatch,
        [
            response(
                completion(tool_call("search_suppliers", {"query": "laptops"}))
            )
        ],
    )

    async def failing_search(_):
        raise RuntimeError("provider unavailable")

    async def unused(_):
        raise AssertionError("scrape should not run")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(
            OpenRouterResearchAgent("secret", "test-model").research(
                "Find suppliers",
                search_suppliers=failing_search,
                scrape_source=unused,
            )
        )