import os
import contextlib
import logging
import uvicorn
# import requests
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Image as MCPImage, Context
from mcp_image_utils import to_mcp_image, retrieve_image_from_url
from PIL import Image as PILImage, ImageOps
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP under a unique path ending with '/'
# to match the configured base URL and prevent redirects.
mcp = FastMCP("negative-image", streamable_http_path="/negative-image/", json_response=True)

# @mcp.tool()
# def example_tool(image_url: str) -> dict:
#     """Returning hello world for testing."""
#     return {"message": f"Hello, world! You sent {image_url}"}

@mcp.tool()
def negative_image(image_url: str) -> MCPImage:
    """Generate a negative image from a URL.

    Pass an HTTP(S) URL to an image. The server downloads it, inverts
    the colors, and returns the processed image as JPEG.
    """
    # Load source image from URL and ensure RGB
    img = retrieve_image_from_url(image_url).convert("RGB")

    # Invert colors
    neg = ImageOps.invert(img)

    # Return as MCP image
    return to_mcp_image(neg, format="jpeg")


# @mcp.tool()
# async def negative_image_from_resource(ctx: Context, resource_uri: str) -> MCPImage:
#     """Generate a negative image from a client-provided resource URI.

#     Pass a resource URI exposed by the MCP client (e.g., an attached file).
#     The server streams the bytes via the MCP session, inverts the image,
#     and returns the result as JPEG.
#     """
#     # Read binary data from the client-managed resource
#     await ctx.debug(f"Reading resource: {resource_uri}")
#     data: bytes = await ctx.read_resource(resource_uri)

#     # Open with PIL and ensure RGB
#     img = PILImage.open(io.BytesIO(data)).convert("RGB")

#     # Invert colors
#     neg = ImageOps.invert(img)

#     # Return as MCP image
#     return to_mcp_image(neg, format="jpeg")

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
        # Behind Caddy: respect X-Forwarded-* and use https in redirects
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=75,
    )

if __name__ == "__main__":
    main()
