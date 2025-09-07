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
import base64
import urllib.parse

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


@mcp.tool()
async def negative_image_from_resource(ctx: Context, resource_uri: str) -> MCPImage:
    """Generate a negative image from a client-provided resource URI.

    Pass a resource URI exposed by the MCP client (e.g., an attached file).
    The server streams the bytes via the MCP session, inverts the image,
    and returns the result as JPEG.
    """
    await ctx.debug(f"Received resource_uri: '{resource_uri}'")
    # Support a few common input forms to reduce user confusion:
    # - http(s)://...               → download directly
    # - data:[mime];base64,...      → parse inline base64
    # - <scheme>://...              → ask client to read resource via MCP
    # - bare IDs (e.g. user_uploaded_file_...) are NOT valid URIs → helpful error

    # Direct HTTP(S) fetch
    if resource_uri.startswith("http://") or resource_uri.startswith("https://"):
        await ctx.debug(f"Fetching HTTP image: {resource_uri}")
        img = retrieve_image_from_url(resource_uri).convert("RGB")

    # Data URI (inline base64 or url-encoded)
    elif resource_uri.startswith("data:"):
        await ctx.debug("Parsing data URI image input")
        try:
            header, payload = resource_uri.split(",", 1)
        except ValueError:
            raise ValueError("Invalid data URI; expected 'data:[mime];base64,<data>'")

        if ";base64" in header:
            data = base64.b64decode(payload)
        else:
            data = urllib.parse.unquote_to_bytes(payload)
        img = PILImage.open(io.BytesIO(data)).convert("RGB")

    # Client-managed resource via MCP (must have a URI scheme, but not HTTP/HTTPS)
    elif "://" in resource_uri and not (resource_uri.startswith("http://") or resource_uri.startswith("https://")):
        await ctx.debug(f"Reading client resource via MCP: {resource_uri}")
        try:
            data: bytes = await ctx.read_resource(resource_uri)
            img = PILImage.open(io.BytesIO(data)).convert("RGB")
        except Exception as e:
            await ctx.error(f"Failed to read resource '{resource_uri}': {e}")
            await ctx.info("To use local files, try one of these approaches:")
            await ctx.info("1. Upload the file to Claude first, then use the https://files.claude.ai/... URL") 
            await ctx.info("2. Convert the file to a data URI (data:image/png;base64,...)")
            await ctx.info("3. Use the negative_image tool with a direct URL instead")
            raise ValueError(f"Could not access resource '{resource_uri}'. The client must expose this resource via MCP protocol.")

    # Bare IDs are not valid URIs
    else:
        await ctx.error(
            f"Expected a resource URI (e.g., file://..., upload://..., data:..., https://...). "
            f"Got: '{resource_uri}'. This likely refers to a client-specific "
            "upload ID (e.g., 'user_uploaded_file_*') which cannot be read without its full URI."
        )
        raise ValueError(
            f"Invalid resource identifier: '{resource_uri}'. Pass a full URI like file://..., upload://..., data:..., or https://..."
        )

    # Invert colors
    neg = ImageOps.invert(img)

    # Return as MCP image
    return to_mcp_image(neg, format="jpeg")

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
