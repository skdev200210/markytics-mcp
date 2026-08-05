"""Read side of the per-turn agent config handoff. Lives in the MCP server repo.

The chatbot writes one turn's agent config to Redis and sends only the turn's id in
the `X-Context-ID` header. This module turns that header back into the config dict,
so `create_agent` gets client_id / product_id / llm_id / ... without those ever
having passed through the model.

The key format here is a contract with the chatbot's `app/core/context_store.py`.
If you change `_KEY_PREFIX`, change it there in the same deploy.

Config, both sides:
    REDIS_URL   must point at the same instance the chatbot writes to
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import redis.asyncio as redis #type: ignore
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers

from app.core.config import settings

# Contract with the chatbot. Must match its _KEY_PREFIX exactly.
_KEY_PREFIX = "agent-chatbot:mcp-ctx:"

# get_http_headers() lowercases every name, so match on the lowercase form.
CONTEXT_ID_HEADER = "x-context-id"

_client: redis.Redis | None = None


async def connect() -> None:
    """Open the connection pool. Call once from the server's lifespan/startup."""
    global _client
    if _client is not None:
        return
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not set; the agent config cannot be read")
    client = redis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    _client = client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def key(context_id: str) -> str:
    """The Redis key the chatbot wrote this turn's config to."""
    return f"{_KEY_PREFIX}{context_id}"


def current_context_id() -> str | None:
    """This turn's context id from the request header, or None if it is absent.

    Returns None rather than raising for a non-HTTP transport (stdio, in-memory
    tests), where there is no request to read a header from.
    """
    return get_http_headers().get(CONTEXT_ID_HEADER) or None


async def get(context_id: str) -> dict[str, Any] | None:
    """Fetch a turn's config, or None if the key is gone.

    A missing key is normal rather than exceptional: it means the TTL lapsed, or the
    chatbot could not reach Redis and sent the config inline instead. Callers should
    treat None as "look elsewhere", not as a failure.

    Does not delete the key. The chatbot runs its agent with `retries=2`, so
    `create_agent` can fire more than once per turn and each attempt re-reads this.
    """
    if _client is None:
        raise RuntimeError("redis pool is not open; call connect() at startup")

    raw = await _client.get(key(context_id))
    if raw is None:
        return None
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"the stored agent config for {context_id} is not valid JSON") from exc
    if not isinstance(config, dict):
        raise ToolError(
            f"the stored agent config for {context_id} is a {type(config).__name__}, expected an object"
        )
    return config


async def resolve_config(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The agent config for this turn, from the inline argument or from Redis.

    `payload` wins when it is present. The chatbot falls back to sending the config
    as a tool argument whenever its Redis write fails, and honouring that here is
    what lets the two services deploy in either order. Once the chatbot has stopped
    sending it, drop the parameter and call `require_context_config()` directly.

    Raises ToolError with a message the model can act on — it is instructed to report
    the failure rather than claim the agent was created.
    """
    if payload:
        return dict(payload)
    return await require_context_config()


async def require_context_config() -> dict[str, Any]:
    """The config from Redis, raising ToolError when it cannot be produced."""
    context_id = current_context_id()
    if context_id is None:
        raise ToolError(
            f"no {CONTEXT_ID_HEADER} header on this request, so the account settings "
            "for the agent could not be looked up"
        )

    config = await get(context_id)
    if config is None:
        raise ToolError(
            "the account settings for this request have expired or were never stored, "
            "so the agent cannot be created; retry the request"
        )
    return config

def require_keys(config: Mapping[str, Any], *names: str) -> None:
    """Fail early when the config is missing ids the workflow API needs.

    Cheaper to surface here as a tool error than as a 4xx from the workflow API with
    a message the model cannot interpret.
    """
    missing = [name for name in names if config.get(name) in (None, "")]
    if missing:
        raise ToolError(
            "the account settings for this request are missing: " + ", ".join(sorted(missing))
        )