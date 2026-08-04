from contextlib import asynccontextmanager

from starlette.applications import Starlette  # type: ignore
from starlette.middleware.cors import CORSMiddleware  # type: ignore
from starlette.routing import Mount

from app.core.config import settings
from app.core.logger import logger
from app.mcp_server import mcp_http
from app.middleware import _NormalizeMcpSlash

@asynccontextmanager
async def lifespan(app):
    """Initialize shared runtime resources on application startup within the Starlette lifespan context."""
    # The mounted MCP transport needs its session manager running for the
    # app's lifetime (the mount does not run the sub-app's own lifespan).
    async with mcp_http.running():
        yield


app = Starlette(
    debug=settings.log_level.upper() == "DEBUG",
    routes=[
        Mount("/mcp", app=mcp_http),
    ],
    lifespan=lifespan,
)

# Added before CORS so CORS (added last = outermost) still stamps 401/503
# auth responses; the guard itself is env-gated (API_AUTH_ENABLED).
app.add_middleware(_NormalizeMcpSlash)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
