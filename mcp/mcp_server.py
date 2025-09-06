# import os
# import contextlib
# import logging
# import uvicorn
import requests
# from starlette.applications import Starlette
# from starlette.routing import Mount, Route
# from starlette.requests import Request
# from starlette.responses import JSONResponse, Response

# from mcp.server.fastmcp import FastMCP

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # Initialize FastMCP server and expose Streamable HTTP at mount root
# mcp = FastMCP("weather", streamable_http_path="/")


# @mcp.tool()
# def current_temperature(lat: float, lon: float) -> dict:
#     """Get current temperature from Open-Meteo API."""
#     url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
#     r = requests.get(url).json()
#     return {"temperature": r["hourly"]["temperature_2m"][0]}


# async def health_check(_: Request) -> Response:
#     return JSONResponse({"status": "healthy", "service": "mcp-weather"})


# # Build the main ASGI app with Streamable HTTP mounted
# mcp_asgi = mcp.streamable_http_app()

# @contextlib.asynccontextmanager
# async def lifespan(_: Starlette):
#     # Ensure FastMCP session manager is running, as required by Streamable HTTP
#     async with mcp.session_manager.run():
#         yield

# app = Starlette(
#     routes=[
#         Route("/health", endpoint=health_check, methods=["GET"]),
#         # Expose MCP at both '/' and '/mcp' for compatibility
#         Mount("/", app=mcp_asgi),
#         Mount("/mcp", app=mcp_asgi),
#     ],
#     lifespan=lifespan,
# )

# def main():
#     """
#     Main function to run the uvicorn server with HTTPS support
#     """
#     PORT = int(os.getenv("PORT", "9000"))
#     SSL_CERTFILE = os.getenv("SSL_CERTFILE", "/etc/ssl/certs/server.crt")
#     SSL_KEYFILE = os.getenv("SSL_KEYFILE", "/etc/ssl/private/server.key")
    
#     logger.info(f"Starting Weather MCP server on port {PORT}")
    
#     uvicorn_kwargs = {
#         "app": app,
#         "host": os.getenv("HOST", "0.0.0.0"),  # bind address
#         "port": PORT,
#         "log_level": os.getenv("LOG_LEVEL", "info"),
#         "access_log": True,
#     }

#     # Check if SSL certificates exist and configure HTTPS
#     if os.path.exists(SSL_CERTFILE) and os.path.exists(SSL_KEYFILE):
#         uvicorn_kwargs["ssl_certfile"] = SSL_CERTFILE
#         uvicorn_kwargs["ssl_keyfile"] = SSL_KEYFILE
#         logger.info(f"HTTPS enabled with certificates: cert={SSL_CERTFILE}, key={SSL_KEYFILE}")
#     else:
#         logger.warning("SSL certificates not found. Running with HTTP only.")
#         logger.warning(f"Expected cert: {SSL_CERTFILE}")
#         logger.warning(f"Expected key: {SSL_KEYFILE}")
#         logger.warning("To enable HTTPS, provide SSL_CERTFILE and SSL_KEYFILE environment variables")

#     uvicorn.run(**uvicorn_kwargs)

# if __name__ == "__main__":
#     main()

# Simplified approach

from mcp.server.fastmcp import FastMCP

# Stateful server (maintains session state)
mcp = FastMCP("StatefulServer")

# Other configuration options:
# Stateless server (no session persistence)
# mcp = FastMCP("StatelessServer", stateless_http=True)

# Stateless server (no session persistence, no sse stream with supported client)
# mcp = FastMCP("StatelessServer", stateless_http=True, json_response=True)

@mcp.tool()
def current_temperature(lat: float, lon: float) -> dict:
    """Get current temperature from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return {"temperature": r["hourly"]["temperature_2m"][0]}


# Run server with streamable_http transport
if __name__ == "__main__":
    mcp.run(transport="streamable-http")