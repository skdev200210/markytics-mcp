from contextlib import asynccontextmanager
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP #type: ignore
from mcp.server.fastmcp.exceptions import ToolError #type: ignore
from mcp.server.transport_security import TransportSecuritySettings #type: ignore
from mcp.server.fastmcp import Context
from fastmcp.server.dependencies import get_http_headers

from app.services.create_agent_service import _post
from app.core.logger import logger
from app.core.config import settings


mcp = FastMCP(
    name="markytics-mcp",
    instructions=(
        """
        MCP Server to create agents using the configurations
        """
    ),
    # Mounted at /mcp by app.main, so the transport itself serves at "/" —
    # otherwise the endpoint would be /mcp/mcp.
    streamable_http_path="/",
    # Each tool call is an independent request; no session state to resume.
    stateless_http=True,
    json_response=True,
    # DNS-rebinding protection guards browser-originated requests via Host
    # checks; this server is reached server-to-server (bound 0.0.0.0, CORS
    # already wide open), where the check only rejects legitimate LAN-IP
    # hosts. Real access control is the planned auth layer, required before
    # any non-local exposure.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
async def create_agent(
    ctx: Context,
    start_message: str,
    end_message: str,
    instructions: str,
    objective: str,
    rules: List[str],
    summary_prompt: str,
    payload: Dict[str, Any],
):
    """
    Create a new Agent from a set of configurations.

    This creates the agent in two steps: first registering an agent-master
    record, then creating the agent itself linked to that master record.

    Args:
        start_message: Opening message the agent speaks/sends when a call or conversation begins.
        end_message: Closing message the agent speaks/sends when a call or conversation ends.
        instructions: Free-form instructions describing how the agent should behave during the conversation.
        objective: The agent's primary objective/goal for the conversation.
        rules: List of rules/constraints the agent must follow during the conversation.
        summary_prompt: Prompt template used to generate a post-call/post-conversation summary.
        payload: Agent configuration dict. Expected keys:
            - agent_name (str): Display name for the agent.
            - client_id (str/int): ID of the client this agent belongs to.
            - template_id (str/int): ID of the template this agent is based on.
            - channel_id (str/int): ID of the communication channel.
            - product_id (str/int): ID of the product this agent is tied to.
            - input_file_id (str/int, optional): ID of the input data file.
            - languages_supported (List[str]): Language codes the agent supports.
            - language_names (List[str]): Human-readable names matching languages_supported.
            - llm_id / llm_name: LLM configuration for the agent.
            - stt_id / stt_name: Speech-to-text configuration.
            - tts_id / tts_name: Text-to-speech configuration.
            - voice (str): Voice ID/name to use for TTS.
            - expected_input_columns (List[str]): Column names expected in the input data file.
            - expected_output_columns (List[str]): Column names to produce in the output/results.

    Returns:
        dict: On success, {"message": "Agent created successfully", "agent_name": <agent_name>}. On failure, {"error": <details>}.
    """
    try:
        headers = get_http_headers()
        context_id = headers.get("x-context-id")   # lowercase key
        logger.info("Context ID received in the tool: %s", context_id)

        logger.info("Received payload for agent creation: %s", payload)

        agent_master_payload = {
            "agent_name": payload.get("agent_name"),
            "client_id": payload.get("client_id"),
            "product_id": payload.get("product_id"),
            "channel_id": payload.get("channel_id"),
        }

        logger.info("agent_master_payload: %s", agent_master_payload)

        agent_master_response = await _post(
            endpoint_url=settings.product_v3_workflow_base_url + "/api/v1/agent-master",
            payload=agent_master_payload,
        )

        logger.info("Agent master created successfully: %s", agent_master_response)

        agent_create_payload = {
            "agent_name": payload.get("agent_name"),
            "agent_master_id": agent_master_response.get("agent_id"),
            "client_id": payload.get("client_id"),
            "product_id": payload.get("product_id"),
            "channel_id": payload.get("channel_id"),
            "parent_agent_id": None,
            "input_file_id": payload.get("input_file_id"),
            "start_msg": start_message,
            "end_msg": end_message,
            "instructions": instructions,
            "rules": rules,
            "objectives": objective,
            "summary_prompt": summary_prompt,
            "is_global_agent": False,

            "languages_supported": payload.get("languages_supported"),
            "language_names": payload.get("languages"),

            "llm_id": payload.get("llm_id"),
            "stt_id": payload.get("stt_id"),
            "tts_id": payload.get("tts_id"),

            "llm_name": payload.get("llm_name"),
            "stt_name": payload.get("stt_name"),
            "tts_name": payload.get("tts_name"),

            "voice": payload.get("voice"),

            "channel_type": "AI_CALL",

            "use_calling_config_defaults": False,

            "expected_input_columns": payload.get("expected_input_columns"),
            "expected_output_columns": payload.get("expected_output_columns"),

            "is_start_template": True
        }

        agent_response = await _post(
            endpoint_url=settings.product_v3_workflow_base_url + "/api/v1/agents",
            payload=agent_create_payload
        )

        logger.info("Agent created successfully: %s", agent_response)
        logger.info("Agent created successfully: %s", agent_create_payload)

        return {
            "message": "Agent created successfully", 
            "agent_name": payload.get("agent_name")
        }
    except ToolError as e:
        logger.error("ToolError occurred: %s", str(e))
        return {"error": str(e)}
    except Exception as e: 
        logger.error("Unexpected error occurred: %s", str(e))
        return {"error": f"Unexpected error: {str(e)}"}




class RestartableStreamableHTTP:
    """Mountable ASGI app + lifespan hook for the MCP streamable-HTTP transport.

    ``StreamableHTTPSessionManager`` is single-run by design, but a Starlette
    lifespan can start more than once in one process (TestClient does this per
    test), so a fresh manager/app pair is built on every startup via
    ``running()`` and torn down with it.
    """

    def __init__(self, server: FastMCP) -> None:
        self._server = server
        self._app = None

    @asynccontextmanager
    async def running(self):
        """Lifespan hook: build a fresh transport and run its session manager."""
        # Discard the spent (or not-yet-built) manager so streamable_http_app()
        # lazily creates a fresh one — the only per-startup state it holds.
        self._server._session_manager = None
        self._app = self._server.streamable_http_app()
        async with self._server.session_manager.run():
            yield

    async def __call__(self, scope, receive, send):
        app = self._app
        if app is None:
            raise RuntimeError(
                "MCP transport request outside the app lifespan — was startup skipped?"
            )
        await app(scope, receive, send)


# Mounted at /mcp in app/main.py; its lifespan runs mcp_http.running().
mcp_http = RestartableStreamableHTTP(mcp)
