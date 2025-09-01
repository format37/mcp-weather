import os
# import shutil
# import glob
from fastapi import FastAPI, HTTPException, Request
from mcp.server.fastmcp import FastMCP
# import traceback
import logging
# import uuid
# import asyncio
import uvicorn
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("weather")

# @mcp.tool()
# async def get_youtube_metadata(url: str) -> dict:
#     """
#     Extract the label (title) and description of a YouTube video given its URL.

#     Args:
#         url (str): The URL of the YouTube video.

#     Returns:
#         dict: A dictionary with 'label' (title) and 'description' of the video.
#     """
#     try:
#         with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
#             info = ydl.extract_info(url, download=False)
#             label = info.get("title", "")
#             description = info.get("description", "")
#             return {"label": label, "description": description}
#     except Exception as e:
#         logger.error(f"Error extracting metadata: {e}")
#         return {"error": str(e)}
def current_temperature(lat: float, lon: float) -> dict:
    """Get current temperature from Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return {"temperature": r["hourly"]["temperature_2m"][0]}

app = FastAPI()

@app.get("/test")
async def test_endpoint():
    """
    Test endpoint to verify the server is running.
    
    Returns:
        dict: A simple response indicating the server status.
    """
    return {
        "status": "ok",
        "message": "YouTube MCP server is running",
        "endpoints": {
            "transcribe": "/transcribe_youtube (MCP tool)",
            "test": "/test"
        }
    }

# @app.on_event("startup")
# async def startup_event():
#     """Clean up data folder on server start"""
#     pass

# @app.middleware("http")
# async def validate_api_key(request: Request, call_next):
#     auth_header = request.headers.get("Authorization")
#     API_KEY = os.environ.get("MCP_KEY")
#     if auth_header != API_KEY:
#         raise HTTPException(status_code=401, detail="Invalid API key")
#     return await call_next(request)

def asgi_sse_wrapper(original_asgi_app):
    async def wrapped_asgi_app(scope, receive, send):
        has_sent_initial_start = False
        
        async def _wrapped_send(message):
            nonlocal has_sent_initial_start
            message_type = message['type']

            if message_type == 'http.response.start':
                if not has_sent_initial_start:
                    has_sent_initial_start = True
                    await send(message)  # Allow the first start message
                else:
                    # Drop subsequent, erroneous start messages
                    pass
            elif message_type == 'http.response.body':
                # Pass through body messages containing SSE data
                await send(message)
            else:
                # Pass through other message types
                await send(message)
        
        await original_asgi_app(scope, receive, _wrapped_send)
    return wrapped_asgi_app

app.mount("/", asgi_sse_wrapper(mcp.sse_app()))

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