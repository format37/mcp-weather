import requests
from typing import Annotated
import asyncio
import json
from mcp.server.fastmcp import FastMCP
import jwt
from jwt.exceptions import InvalidTokenError
from dotenv import load_dotenv
import os
import logging
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()  # Load .env for secrets

# OAuth settings for Auth0
ISSUER_URL = os.getenv("ISSUER_URL")
AUDIENCE = os.getenv("AUDIENCE")
ALGORITHM = "RS256"

logger.info(f"ISSUER_URL: {ISSUER_URL}")
logger.info(f"AUDIENCE: {AUDIENCE}")

# Your weather tool function
def current_temperature(lat: float, lon: float):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m"
    r = requests.get(url).json()
    return r["hourly"]["temperature_2m"][0]

# Token verification function for Auth0 JWT
def verify_auth0_token(token: str):
    try:
        logger.info(f"Verifying token: {token[:20]}...")
        
        # Get JWKS from Auth0
        jwks_url = f"{ISSUER_URL}/.well-known/jwks.json"
        jwks_response = requests.get(jwks_url, timeout=10)
        jwks_response.raise_for_status()
        jwks = jwks_response.json()
        
        # Get key ID from token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        # Find matching key
        public_key = None
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break
        
        if not public_key:
            logger.error(f"No matching key found for kid: {kid}")
            return None
        
        # Verify token
        payload = jwt.decode(
            token, 
            public_key, 
            algorithms=[ALGORITHM], 
            audience=AUDIENCE, 
            issuer=ISSUER_URL
        )
        
        logger.info(f"Token verified for subject: {payload.get('sub')}")
        return payload
        
    except InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
        return None
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return None

# Custom middleware for OAuth authentication
class OAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
            
        # Check for Authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                content=json.dumps({"error": "Missing or invalid authorization header"}),
                status_code=401,
                headers={"content-type": "application/json"}
            )
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        user_payload = verify_auth0_token(token)
        
        if not user_payload:
            return Response(
                content=json.dumps({"error": "Invalid token"}),
                status_code=401,
                headers={"content-type": "application/json"}
            )
        
        # Add user info to request state for use in handlers
        request.state.user = user_payload
        return await call_next(request)

# Initialize FastMCP
mcp = FastMCP(name="Weather MCP Server")

# Expose the weather tool as an MCP tool 
@mcp.tool()
async def get_current_temperature(lat: Annotated[float, "Latitude"], lon: Annotated[float, "Longitude"]) -> float:
    """Fetches the current temperature at the given latitude and longitude."""
    logger.info(f"Fetching temperature for lat={lat}, lon={lon}")
    return current_temperature(lat, lon)

# Create FastAPI app with middleware
def create_app():
    app = FastAPI(title="Weather MCP Server with OAuth")
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://claude.ai", "https://*.claude.ai", "http://localhost:*"], # ToDo: Check other providers too
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Add OAuth middleware
    app.add_middleware(OAuthMiddleware)
    
    # Mount the MCP server
    from starlette.applications import Starlette
    from starlette.routing import Mount
    
    # Get the MCP app
    mcp_app = mcp.streamable_http_app()
    app.mount("/mcp", mcp_app)
    
    return app

# Create the app instance at module level for uvicorn
app = create_app()

if __name__ == "__main__":
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    PORT = int(os.getenv("PORT", "9000"))
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
