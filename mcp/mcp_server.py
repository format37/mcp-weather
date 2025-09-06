import os
import contextlib
import logging
from typing import Iterable

import uvicorn
import requests
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server.fastmcp import FastMCP, Context

from pydantic_ai import Agent
from pydantic_ai.models.mcp_sampling import MCPSamplingModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("weather")

# Initialize Pydantic AI agent for weather analysis
weather_agent = Agent(
    system_prompt=(
        'You are a weather assistant. You analyze weather data and provide helpful, '
        'conversational responses about weather conditions. Always include the '
        'temperature and any relevant context about the weather.'
    )
)

@mcp.tool()
def current_temperature(lat: float, lon: float) -> dict:
    """Get current temperature from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return {"temperature": r["hourly"]["temperature_2m"][0]}

@mcp.tool()
async def weather_assistant(ctx: Context, lat: float, lon: float, query: str = "What's the weather like?") -> str:
    """Get weather information with AI-powered analysis using Pydantic AI and MCP sampling."""
    # Get raw weather data
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&hourly=temperature_2m&forecast_days=1"
    response = requests.get(url)
    weather_data = response.json()
    
    # Use Pydantic AI agent with MCP sampling to analyze the weather
    prompt = f"""
    Analyze this weather data for location (lat: {lat}, lon: {lon}) and respond to: "{query}"
    
    Weather data: {weather_data}
    
    Please provide a helpful, conversational response about the weather conditions.
    """
    
    # Use MCPSamplingModel to proxy LLM calls through the client
    result = await weather_agent.run(prompt, model=MCPSamplingModel(session=ctx.session))
    return result.output

def _parse_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


class OriginValidationMiddleware:
    """
    Strict Origin validation middleware for MCP Streamable HTTP.

    - Enforces that requests come from an allowed Origin (env: ALLOWED_ORIGINS).
    - Applies to GET/POST/DELETE on the MCP endpoint (mounted at '/').
    - OPTIONS requests pass through (handled by CORSMiddleware).
    - Allows missing Origin only if ALLOW_NO_ORIGIN=true (default True for
      compatibility with non-browser clients like Claude Desktop).
    """

    def __init__(self, app: Starlette, allowed_origins: Iterable[str], allow_no_origin: bool = True):
        self.app = app
        self.allowed = set(allowed_origins)
        self.allow_no_origin = allow_no_origin

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET").upper()
        # Let CORSMiddleware handle preflight
        if method == "OPTIONS":
            return await self.app(scope, receive, send)

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        origin = headers.get("origin")

        if origin is None:
            if not self.allow_no_origin:
                res = JSONResponse({"error": "Origin required"}, status_code=403)
                return await res(scope, receive, send)
            # Allowed (e.g., non-browser clients)
            return await self.app(scope, receive, send)

        # Exact match check (no wildcarding to satisfy MUST-validate guidance)
        if origin not in self.allowed:
            res = JSONResponse({"error": "Origin not allowed"}, status_code=403)
            return await res(scope, receive, send)

        return await self.app(scope, receive, send)


async def health_check(_: Request) -> Response:
    return JSONResponse({"status": "healthy", "service": "mcp-weather"})


# Build the main ASGI app with Streamable HTTP mounted at '/'
mcp_asgi = mcp.streamable_http_app()


class _RootToMcpForwarder:
    """Forward '/' requests to '/mcp' for compatibility with clients.

    Some clients POST/GET the MCP endpoint at '/', while others expect '/mcp'.
    This ASGI app rewrites the incoming path to '/mcp' and delegates to the
    underlying MCP ASGI app.
    """

    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.inner_app(scope, receive, send)
        # Only rewrite exact root path; leave other paths untouched
        path = scope.get("path", "/")
        if path == "/":
            new_scope = dict(scope)
            new_scope["path"] = "/mcp"
            if "raw_path" in new_scope:
                new_scope["raw_path"] = b"/mcp"
            return await self.inner_app(new_scope, receive, send)
        return await self.inner_app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(_: Starlette):
    # Ensure FastMCP session manager is running, as required by Streamable HTTP
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/health", endpoint=health_check, methods=["GET"]),
        # Native MCP mount at '/mcp'
        Mount("/mcp", app=mcp_asgi),
        # Compatibility: forward root '/' to '/mcp'
        Mount("/", app=_RootToMcpForwarder(mcp_asgi)),
    ],
    lifespan=lifespan,
)

# Configure CORS and Origin validation per Streamable HTTP guidance
ALLOWED_ORIGINS = _parse_env_list(os.getenv("ALLOWED_ORIGINS"))
# If you know you will only be called from Claude Web, you can set:
#   ALLOWED_ORIGINS="https://claude.ai,https://web.staging-v2.0.claude.ai"

ALLOW_NO_ORIGIN = os.getenv("ALLOW_NO_ORIGIN", "true").lower() in {"1", "true", "yes", "y"}

# CORS middleware first (adds headers and handles preflight)
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Authorization",
            "Mcp-Session-Id",
            "Last-Event-ID",
            "Origin",
            "User-Agent",
        ],
        expose_headers=["Mcp-Session-Id"],
        allow_credentials=False,
        max_age=600,
    )

# Then strict Origin validation (MUST validate Origin on incoming connections)
app.add_middleware(OriginValidationMiddleware, allowed_origins=ALLOWED_ORIGINS, allow_no_origin=ALLOW_NO_ORIGIN)

def main():
    """
    Main function to run the uvicorn server with HTTPS support
    """
    PORT = int(os.getenv("PORT", "9000"))
    SSL_CERTFILE = os.getenv("SSL_CERTFILE", "/etc/ssl/certs/server.crt")
    SSL_KEYFILE = os.getenv("SSL_KEYFILE", "/etc/ssl/private/server.key")
    
    logger.info(f"Starting Weather MCP server on port {PORT}")
    
    uvicorn_kwargs = {
        "app": app,
        "host": os.getenv("HOST", "0.0.0.0"),  # bind address
        "port": PORT,
        "log_level": os.getenv("LOG_LEVEL", "info"),
        "access_log": True,
        # HTTP/1.1 is fine for SSE; h2 disabled by default in Uvicorn
        # Increase timeouts for long-lived SSE connections if desired
        # "timeout_keep_alive": int(os.getenv("TIMEOUT_KEEP_ALIVE", "5")),
        # "timeout_notify": int(os.getenv("TIMEOUT_NOTIFY", "30")),
    }

    # Check if SSL certificates exist and configure HTTPS
    if os.path.exists(SSL_CERTFILE) and os.path.exists(SSL_KEYFILE):
        uvicorn_kwargs["ssl_certfile"] = SSL_CERTFILE
        uvicorn_kwargs["ssl_keyfile"] = SSL_KEYFILE
        logger.info(f"HTTPS enabled with certificates: cert={SSL_CERTFILE}, key={SSL_KEYFILE}")
    else:
        logger.warning("SSL certificates not found. Running with HTTP only.")
        logger.warning(f"Expected cert: {SSL_CERTFILE}")
        logger.warning(f"Expected key: {SSL_KEYFILE}")
        logger.warning("To enable HTTPS, provide SSL_CERTFILE and SSL_KEYFILE environment variables")

    uvicorn.run(**uvicorn_kwargs)

if __name__ == "__main__":
    main()
