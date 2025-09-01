import os
import contextlib
from starlette.applications import Starlette
from starlette.routing import Host
from mcp.server.fastmcp import FastMCP
import logging
import uvicorn
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("weather")

@mcp.tool()
def current_temperature(lat: float, lon: float) -> dict:
    """Get current temperature from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return {"temperature": r["hourly"]["temperature_2m"][0]}

# Create a lifespan to manage the session manager
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

# Mount using Host-based routing with lifespan management
app = Starlette(
    routes=[
        Host("rtlm.info", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)

def main():
    """
    Main function to run the uvicorn server
    """
    PORT = int(os.getenv("PORT", "5000"))
    SSL_CERTFILE = os.getenv("SSL_CERTFILE", None)
    SSL_KEYFILE = os.getenv("SSL_KEYFILE", None)

    uvicorn_kwargs = {
        "app": app,
        "host": "0.0.0.0",
        "port": PORT,
        "log_level": "info"
    }

    if SSL_CERTFILE and SSL_KEYFILE:
        uvicorn_kwargs["ssl_certfile"] = SSL_CERTFILE
        uvicorn_kwargs["ssl_keyfile"] = SSL_KEYFILE

    uvicorn.run(**uvicorn_kwargs)

if __name__ == "__main__":
    main()