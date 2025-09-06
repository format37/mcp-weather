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

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Optionally suppress noisy library warnings that are benign during normal MCP flows
_suppress = os.getenv("SUPPRESS_MCP_WARNINGS", "true").lower() in {"1", "true", "yes", "y"}
if _suppress:
    class _McpNoiseFilter(logging.Filter):
        _prefixes = (
            "Failed to validate request: Received request before initialization was complete",
            "Failed to validate notification: RequestResponder must be used as a context manager",
        )

        def filter(self, record: logging.LogRecord) -> bool:
            msg = str(record.getMessage())
            return not any(msg.startswith(p) for p in self._prefixes)

    logging.getLogger().addFilter(_McpNoiseFilter())

# Initialize FastMCP server and expose Streamable HTTP at mount root
mcp = FastMCP("weather", streamable_http_path="/")


@mcp.tool()
def current_temperature(lat: float, lon: float) -> dict:
    """Get current temperature from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return {"temperature": r["hourly"]["temperature_2m"][0]}

## Removed the AI-based weather_assistant tool for a minimal example.

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


# Build the main ASGI app with Streamable HTTP mounted
mcp_asgi = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(_: Starlette):
    # Ensure FastMCP session manager is running, as required by Streamable HTTP
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/health", endpoint=health_check, methods=["GET"]),
        # Expose MCP at both '/' and '/mcp' for compatibility
        Mount("/", app=mcp_asgi),
        Mount("/mcp", app=mcp_asgi),
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
        allow_methods=["GET", "POST", "DELETE"],  # OPTIONS handled automatically
        allow_headers=["*"],  # Allow any requested header from Claude Web
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
