import os
import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP, Context
import logging
import uvicorn
import requests

from pydantic_ai import Agent
from pydantic_ai.models.mcp_sampling import MCPSamplingModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("weather")

# Initialize Pydantic AI agent with MCP sampling support
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
    """Get weather information with AI-powered analysis using MCP sampling."""
    # Get raw weather data
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&hourly=temperature_2m&forecast_days=1"
    response = requests.get(url)
    weather_data = response.json()
    
    # Use the Pydantic AI agent with MCP sampling to analyze the weather
    prompt = f"""
    Analyze this weather data for location (lat: {lat}, lon: {lon}) and respond to: "{query}"
    
    Weather data: {weather_data}
    
    Please provide a helpful, conversational response about the weather conditions.
    """
    
    result = await weather_agent.run(prompt, model=MCPSamplingModel(session=ctx.session))
    return result.output

# # Create a lifespan to manage the session manager
# @contextlib.asynccontextmanager
# async def lifespan(app: Starlette):
#     async with mcp.session_manager.run():
#         yield

# Mount using Host-based routing with lifespan management
app = Starlette(
    routes=[
        Mount("/", app=mcp.streamable_http_app()),
    ]
    # ,
    # lifespan=lifespan,
)

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
        "host": "0.0.0.0",
        "port": PORT,
        "log_level": "info",
        "access_log": True,
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