import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import httpx


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_MODEL_TURNS = 6
MAX_RESEARCH_ACTIONS = 4
MAX_SCRAPE_ACTIONS = 3
MAX_QUERY_LENGTH = 500
MAX_SCRAPE_CONTENT_LENGTH = 4000

SearchAction = Callable[[str], Awaitable[list[dict[str, Any]]]]
ScrapeAction = Callable[[str], Awaitable[dict[str, Any]]]

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_suppliers",
            "description": "Search suppliers for the procurement.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_source",
            "description": "Read a source URL returned by supplier search.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
]


class ResearchAgentError(RuntimeError):
    """A safe, user-displayable research-agent failure."""


class OpenRouterResearchAgent:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 45.0,
    ):
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        if not model:
            raise ValueError("OpenRouter model is required")

        self._api_key = api_key
        self.model = model
        self.timeout = timeout

    async def research(
        self,
        procurement_brief: str,
        *,
        search_suppliers: SearchAction,
        scrape_source: ScrapeAction,
    ) -> None:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Research suppliers for the procurement. You must call "
                    "search_suppliers before finishing. You may then call "
                    "scrape_source for URLs returned by that search, one at a "
                    "time. Use tool results as evidence, and do not invent "
                    "facts, offers, prices, or eligibility decisions. "
                    "Finish by responding without a tool call when research "
                    "is sufficient."
                ),
            },
            {"role": "user", "content": procurement_brief},
        ]
        searched = False
        scraped_urls: set[str] = set()
        allowed_sources: set[str] = set()
        action_count = 0

        for _ in range(MAX_MODEL_TURNS):
            response_data = await self._complete(messages)
            message = _assistant_message(response_data)
            tool_calls = message.get("tool_calls")

            if not tool_calls:
                if not searched:
                    raise ResearchAgentError(
                        "Research agent finished without searching suppliers."
                    )
                return

            if not isinstance(tool_calls, list) or len(tool_calls) != 1:
                raise ResearchAgentError(
                    "OpenRouter returned malformed tool calls."
                )

            tool_call = tool_calls[0]
            if not isinstance(tool_call, dict):
                raise ResearchAgentError(
                    "OpenRouter returned a malformed tool call."
                )

            call_id = tool_call.get("id")
            function = tool_call.get("function")
            if not isinstance(call_id, str) or not isinstance(function, dict):
                raise ResearchAgentError(
                    "OpenRouter returned a malformed tool call."
                )

            name = function.get("name")
            arguments = _parse_arguments(function.get("arguments"))
            messages.append(message)

            if arguments is None:
                tool_result = {"error": "Tool arguments must be a JSON object."}
            elif name == "search_suppliers":
                query = arguments.get("query")
                if (
                    set(arguments) != {"query"}
                    or not isinstance(query, str)
                    or not query.strip()
                    or len(query) > MAX_QUERY_LENGTH
                ):
                    tool_result = {
                        "error": "query must be a non-empty string of at most 500 characters."
                    }
                elif searched:
                    tool_result = {"error": "Supplier search limit reached."}
                elif action_count >= MAX_RESEARCH_ACTIONS:
                    break
                else:
                    results = await search_suppliers(query.strip())
                    searched = True
                    action_count += 1
                    allowed_sources = {
                        item["url"]
                        for item in results
                        if isinstance(item, dict)
                        and isinstance(item.get("url"), str)
                        and _is_http_url(item["url"])
                    }
                    tool_result = {"sources": _bounded_sources(results)}
            elif name == "scrape_source":
                url = arguments.get("url")
                if (
                    set(arguments) != {"url"}
                    or not isinstance(url, str)
                    or url not in allowed_sources
                    or not _is_http_url(url)
                ):
                    tool_result = {
                        "error": "url must exactly match a URL returned by supplier search."
                    }
                elif url in scraped_urls:
                    tool_result = {"error": "Source has already been scraped."}
                elif len(scraped_urls) >= MAX_SCRAPE_ACTIONS:
                    tool_result = {"error": "Source-scrape limit reached."}
                elif action_count >= MAX_RESEARCH_ACTIONS:
                    break
                else:
                    result = await scrape_source(url)
                    scraped_urls.add(url)
                    action_count += 1
                    tool_result = _bounded_scrape_result(result)
            else:
                tool_result = {"error": "Unknown research tool."}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(
                        tool_result,
                        ensure_ascii=True,
                        default=str,
                    ),
                }
            )

        if not searched:
            raise ResearchAgentError(
                "Research agent reached its turn limit without searching suppliers."
            )

    async def _complete(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    OPENROUTER_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "tools": _TOOLS,
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ResearchAgentError(
                f"OpenRouter returned HTTP {exc.response.status_code}."
            ) from None
        except httpx.TimeoutException:
            raise ResearchAgentError("OpenRouter request timed out.") from None
        except httpx.RequestError as exc:
            raise ResearchAgentError(
                f"OpenRouter request failed ({type(exc).__name__})."
            ) from None

        try:
            payload = response.json()
        except ValueError:
            raise ResearchAgentError("OpenRouter returned malformed JSON.") from None

        if not isinstance(payload, dict):
            raise ResearchAgentError("OpenRouter returned a malformed response.")
        return payload


def _assistant_message(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ResearchAgentError("OpenRouter response contained no usable choices.")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ResearchAgentError("OpenRouter response contained no usable message.")
    return message


def _parse_arguments(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _bounded_sources(sources: Any) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        return []

    bounded = []
    for source in sources[:MAX_SCRAPE_ACTIONS]:
        if not isinstance(source, dict):
            continue
        bounded.append(
            {
                "url": source.get("url"),
                "title": _truncate(source.get("title"), 300),
                "snippet": _truncate(source.get("snippet"), 700),
            }
        )
    return bounded


def _bounded_scrape_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"error": "Source scrape returned an invalid result."}
    return {
        "url": result.get("url"),
        "title": _truncate(result.get("title"), 300),
        "content": _truncate(
            result.get("content"),
            MAX_SCRAPE_CONTENT_LENGTH,
        ),
    }


def _truncate(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit]