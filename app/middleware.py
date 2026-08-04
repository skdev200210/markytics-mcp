
class _NormalizeMcpSlash:
    """Serve /mcp without the 307 → /mcp/ redirect that trips MCP connectors."""
    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = dict(scope, path="/mcp/", raw_path=b"/mcp/")
        await self._app(scope, receive, send)