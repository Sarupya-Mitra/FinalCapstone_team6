"""
Thin OpenRouter chat-completions client (stdlib only).

All failures are raised as AIAgentError with a `run_status` that matches the
extraction_runs.status constraint: 'failed', 'timeout' or 'rate_limited'.
Error messages never contain the API key.
"""
import json
import re
import socket
import urllib.error
import urllib.request

from agent import config


class AIAgentError(Exception):
    def __init__(self, message: str, run_status: str = "failed"):
        super().__init__(message)
        self.run_status = run_status


def chat_completion(messages: list[dict], max_tokens: int = 2000) -> str:
    """Send a chat request to OpenRouter and return the assistant text."""
    if not config.OPENROUTER_API_KEY:
        raise AIAgentError("OpenRouter API key is not configured")

    payload = {
        "model": config.AI_MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        f"{config.OPENROUTER_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": config.OPENROUTER_SITE_URL,
            "X-Title": config.OPENROUTER_APP_NAME,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=config.OPENROUTER_TIMEOUT
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise AIAgentError("AI provider rate limit reached", "rate_limited") from None
        if e.code in (401, 403):
            raise AIAgentError("AI provider rejected the API credentials") from None
        if e.code == 402:
            raise AIAgentError("AI provider account has insufficient credits") from None
        if e.code in (408, 504):
            raise AIAgentError("AI provider request timed out", "timeout") from None
        raise AIAgentError(f"AI provider returned HTTP {e.code}") from None
    except (TimeoutError, socket.timeout):
        raise AIAgentError("AI provider request timed out", "timeout") from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise AIAgentError("AI provider request timed out", "timeout") from None
        raise AIAgentError("AI provider is unreachable") from None
    except (ValueError, UnicodeDecodeError):
        raise AIAgentError("AI provider returned an invalid response") from None

    # OpenRouter can report upstream errors inside a 200 response
    if isinstance(body, dict) and body.get("error"):
        error = body["error"] if isinstance(body["error"], dict) else {}
        if error.get("code") == 429:
            raise AIAgentError("AI provider rate limit reached", "rate_limited")
        raise AIAgentError(
            f"AI provider error: {str(error.get('message', 'unknown'))[:200]}"
        )

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIAgentError("AI provider returned no completion") from None

    if not content or not content.strip():
        raise AIAgentError("AI provider returned an empty completion")
    return content


def parse_json_response(content: str):
    """Parse JSON from model output, tolerating ```json fences / extra prose."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        return json.loads(text)
    except ValueError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            pass
    raise AIAgentError("AI response was not valid JSON")
