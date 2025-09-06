import os
import datetime
import logging
import contextlib
from typing import Any, Iterable, Literal

import click
import requests
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.middleware.cors import CORSMiddleware

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import FastMCP
from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)

# Optional suppression for benign MCP validation warnings
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


class IntrospectionTokenVerifier(TokenVerifier):
    """Token verifier that uses OAuth 2.0 Token Introspection (RFC 7662)."""

    def __init__(
        self,
        introspection_endpoint: str,
        server_url: str,
        validate_resource: bool = False,
    ):
        self.introspection_endpoint = introspection_endpoint
        self.server_url = server_url
        self.validate_resource = validate_resource

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify token via introspection endpoint."""
        import httpx

        # Validate URL to prevent SSRF attacks
        if not self.introspection_endpoint.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            logger.warning(f"Rejecting introspection endpoint with unsafe scheme: {self.introspection_endpoint}")
            return None

        # Configure secure HTTP client
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

        async with httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            verify=True,  # Enforce SSL verification
        ) as client:
            try:
                response = await client.post(
                    self.introspection_endpoint,
                    data={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.debug(f"Token introspection returned status {response.status_code}")
                    return None

                data = response.json()
                if not data.get("active", False):
                    return None

                return AccessToken(
                    token=token,
                    client_id=data.get("client_id", "unknown"),
                    scopes=data.get("scope", "").split() if data.get("scope") else [],
                    expires_at=data.get("exp"),
                    resource=data.get("aud"),
                )
            except Exception as e:
                logger.warning(f"Token introspection failed: {e}")
                return None


class ResourceServerSettings(BaseSettings):
    """Settings for the MCP Resource Server."""

    model_config = SettingsConfigDict(env_prefix="MCP_RESOURCE_")

    # Server settings
    host: str = "0.0.0.0"
    port: int = 9000
    server_url: AnyHttpUrl = AnyHttpUrl("https://rtlm.info:9000")

    # Authorization Server settings
    auth_server_url: AnyHttpUrl = AnyHttpUrl("https://rtlm.info:9001")
    auth_server_introspection_endpoint: str = "https://rtlm.info:9001/introspect"

    # MCP settings
    mcp_scope: str = "user"

    # RFC 8707 resource validation
    oauth_strict: bool = False


def _parse_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


class OriginValidationMiddleware:
    """
    Strict Origin validation for Streamable HTTP per MCP spec.
    """

    def __init__(self, app: Starlette, allowed_origins: Iterable[str], allow_no_origin: bool = True):
        self.app = app
        self.allowed = set(allowed_origins)
        self.allow_no_origin = allow_no_origin

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET").upper()
        if method == "OPTIONS":  # let CORS middleware handle preflight
            return await self.app(scope, receive, send)

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        origin = headers.get("origin")

        if origin is None:
            if not self.allow_no_origin:
                res = JSONResponse({"error": "Origin required"}, status_code=403)
                return await res(scope, receive, send)
            return await self.app(scope, receive, send)

        if origin not in self.allowed:
            res = JSONResponse({"error": "Origin not allowed"}, status_code=403)
            return await res(scope, receive, send)

        return await self.app(scope, receive, send)

def current_temperature(lat: float, lon: float):
    """Get current temperature from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return r["hourly"]["temperature_2m"][0]


def create_resource_server(settings: ResourceServerSettings) -> FastMCP:
    """
    Create MCP Resource Server with token introspection.

    This server:
    1. Provides protected resource metadata (RFC 9728)
    2. Validates tokens via Authorization Server introspection
    3. Serves MCP tools and resources
    """
    # Create token verifier for introspection
    token_verifier = IntrospectionTokenVerifier(
        introspection_endpoint=settings.auth_server_introspection_endpoint,
        server_url=str(settings.server_url),
        validate_resource=settings.oauth_strict,
    )

    # Create FastMCP server as a Resource Server
    app = FastMCP(
        name="Weather MCP Resource Server",
        instructions="Resource Server that validates tokens via Authorization Server introspection",
        host=settings.host,
        port=settings.port,
        debug=True,
        streamable_http_path="/",  # mount at root of any Starlette mount
        # Auth configuration for RS mode
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.auth_server_url,
            required_scopes=[settings.mcp_scope],
            resource_server_url=settings.server_url,
        ),
    )

    @app.tool()
    async def get_current_temperature(lat: float, lon: float) -> float:
        """
        Fetches the current temperature at the given latitude and longitude.
        
        This tool demonstrates weather data access protected by OAuth authentication.
        User must be authenticated to access it.
        """
        logger.info(f"Fetching temperature for lat={lat}, lon={lon}")
        return current_temperature(lat, lon)

    @app.tool()
    async def get_time() -> dict[str, Any]:
        """
        Get the current server time.

        This tool demonstrates that system information can be protected
        by OAuth authentication. User must be authenticated to access it.
        """
        now = datetime.datetime.now()

        return {
            "current_time": now.isoformat(),
            "timezone": "UTC",
            "timestamp": now.timestamp(),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

    return app


@click.command()
@click.option("--port", default=9000, help="Port to listen on")
@click.option("--auth-server", default="http://localhost:9001", help="Authorization Server URL")
@click.option(
    "--transport",
    default="sse",
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use ('sse' or 'streamable-http')",
)
@click.option(
    "--oauth-strict",
    is_flag=True,
    help="Enable RFC 8707 resource validation",
)
def main(port: int, auth_server: str, transport: Literal["sse", "streamable-http"], oauth_strict: bool) -> int:
    """
    Run the MCP Resource Server.

    This server:
    - Provides RFC 9728 Protected Resource Metadata
    - Validates tokens via Authorization Server introspection
    - Serves MCP tools requiring authentication

    Must be used with a running Authorization Server.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        # Parse auth server URL
        auth_server_url = AnyHttpUrl(auth_server)

        # Create settings
        host = "0.0.0.0"
        server_url = f"https://rtlm.info:{port}"
        settings = ResourceServerSettings(
            host=host,
            port=port,
            server_url=AnyHttpUrl(server_url),
            auth_server_url=auth_server_url,
            auth_server_introspection_endpoint=f"{auth_server}/introspect",
            oauth_strict=oauth_strict,
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Make sure to provide a valid Authorization Server URL")
        return 1

    try:
        mcp_server = create_resource_server(settings)

        logger.info(f"🚀 MCP Resource Server running on {settings.server_url}")
        logger.info(f"🔑 Using Authorization Server: {settings.auth_server_url}")

        # Check for SSL certificates
        ssl_certfile = os.getenv("SSL_CERTFILE")
        ssl_keyfile = os.getenv("SSL_KEYFILE")
        
        if ssl_certfile and ssl_keyfile:
            logger.info(f"🔒 SSL enabled with cert: {ssl_certfile}")

            if transport == "streamable-http":
                import uvicorn

                # Get the streamable HTTP app from FastMCP
                mcp_app = mcp_server.streamable_http_app()

                # Health endpoint
                async def health_check(request):
                    return JSONResponse({"status": "healthy", "service": "mcp-weather-resource-server"})

                # Starlette lifespan to run session manager
                @contextlib.asynccontextmanager
                async def lifespan(_: Starlette):
                    async with mcp_server.session_manager.run():
                        yield

                # Main app mounting MCP at both '/' and '/mcp'
                main_app = Starlette(
                    routes=[
                        Route("/health", endpoint=health_check, methods=["GET"]),
                        Mount("/", app=mcp_app),
                        Mount("/mcp", app=mcp_app),
                    ],
                    lifespan=lifespan,
                )

                # CORS and Origin validation
                allowed_origins = _parse_env_list(os.getenv("ALLOWED_ORIGINS"))
                allow_no_origin = os.getenv("ALLOW_NO_ORIGIN", "true").lower() in {"1", "true", "yes", "y"}
                if allowed_origins:
                    main_app.add_middleware(
                        CORSMiddleware,
                        allow_origins=allowed_origins,
                        allow_methods=["GET", "POST", "DELETE"],
                        allow_headers=["*"],
                        expose_headers=["Mcp-Session-Id"],
                        allow_credentials=False,
                        max_age=600,
                    )
                main_app.add_middleware(
                    OriginValidationMiddleware, allowed_origins=allowed_origins, allow_no_origin=allow_no_origin
                )

                uvicorn.run(
                    main_app,
                    host=settings.host,
                    port=settings.port,
                    ssl_certfile=ssl_certfile,
                    ssl_keyfile=ssl_keyfile,
                    log_level="info",
                )
            else:
                mcp_server.run(transport=transport)
        else:
            mcp_server.run(transport=transport)
            
        logger.info("Server stopped")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    main()
