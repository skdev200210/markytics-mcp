from typing import Any, Dict, List
from mcp.server.fastmcp.exceptions import ToolError #type: ignore

import httpx #type: ignore


async def _post(endpoint_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a POST request to the specified endpoint with the given payload.

    Args:
        endpoint_url (str): The URL of the endpoint to send the request to.
        payload (Dict[str, Any]): The payload to send in the request.

    Returns:
        Dict[str, Any]: The JSON response from the endpoint.

    Raises:
        ToolError: If the request fails or the response is not valid JSON.
    """

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(endpoint_url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            raise ToolError(f"Request error: {e}")
        except httpx.HTTPStatusError as e:
            raise ToolError(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except ValueError as e:
            raise ToolError(f"Invalid JSON response: {e}")