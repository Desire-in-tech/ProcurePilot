import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings


API_URL = "https://openrouter.ai/api/v1/chat/completions"


def main() -> int:
    api_key = (settings.openrouter_api_key or "").strip()
    model = settings.openrouter_model.strip()
    missing = [
        name
        for name, value in (
            ("OPENROUTER_API_KEY", api_key),
            ("OPENROUTER_MODEL", model),
        )
        if not value
    ]
    if missing:
        print(f"Missing required environment variable(s): {', '.join(missing)}")
        return 2

    request_body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Begin supplier research for business laptops. "
                    "Use the search_suppliers tool to search for reputable suppliers."
                ),
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_suppliers",
                    "description": "Search for suppliers matching a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "search_suppliers"},
        },
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_body,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            print("OpenRouter rate limit reached (HTTP 429). Try again later.")
        else:
            print(f"OpenRouter returned HTTP {exc.response.status_code}.")
            body = exc.response.text[:1500]
            if body:
                print(f"Error details: {body}")
        return 1
    except httpx.TimeoutException:
        print("OpenRouter request timed out.")
        return 1
    except httpx.RequestError as exc:
        print(f"OpenRouter request failed ({type(exc).__name__}).")
        return 1

    try:
        result = response.json()
    except ValueError:
        print("OpenRouter returned malformed JSON.")
        return 1

    if not isinstance(result, dict):
        print("OpenRouter returned a malformed response.")
        return 1

    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        print("OpenRouter response contained no usable choices.")
        return 1

    message = choices[0].get("message")
    tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(tool_calls, list) or not tool_calls:
        print("No tool call returned. The model did not call search_suppliers.")
        return 0

    tool_call = tool_calls[0]
    function = tool_call.get("function") if isinstance(tool_call, dict) else None
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        print("OpenRouter returned a malformed tool call.")
        return 1

    try:
        arguments = json.loads(function.get("arguments", ""))
    except (TypeError, ValueError):
        print("OpenRouter returned malformed tool-call arguments.")
        return 1

    if not isinstance(arguments, dict):
        print("OpenRouter returned malformed tool-call arguments.")
        return 1

    print(f"Tool: {function['name']}")
    print(f"Arguments: {json.dumps(arguments, ensure_ascii=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
