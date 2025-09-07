import os
import contextlib
import logging
import uvicorn
import requests
from starlette.applications import Starlette
from starlette.routing import Mount

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server under a unique path to avoid cookie/session collisions
# when multiple MCPs are hosted on the same domain behind the gateway.
mcp = FastMCP("negative-image", streamable_http_path="/negative-image")

@mcp.tool()
def example_tool(image_url: str) -> dict:
    """Returning hello world for testing."""
    return {"message": f"Hello, world! You sent {image_url}"}

# Build the main ASGI app with Streamable HTTP mounted
mcp_asgi = mcp.streamable_http_app()

@contextlib.asynccontextmanager
async def lifespan(_: Starlette):
    # Ensure FastMCP session manager is running, as required by Streamable HTTP
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[
        Mount("/", app=mcp_asgi),
    ],
    lifespan=lifespan,
)

def main():
    """
    Run the uvicorn server without SSL (TLS handled by Caddy).
    """
    PORT = int(os.getenv("PORT", "8002"))

    logger.info(f"Starting Negative-Image MCP server (HTTP) on port {PORT}")

    uvicorn.run(
        app=app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=PORT,
        log_level=os.getenv("LOG_LEVEL", "info"),
        access_log=True,
    )

if __name__ == "__main__":
    main()
