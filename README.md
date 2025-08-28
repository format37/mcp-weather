# mcp-weather
A simple weather MCP example, that using Docker, OAuth, Python, SSL  
* Input: lat, lon
* Output: temperature
# mcp/.env
Register your app on [auth0.com](https://manage.auth0.com)  
Put the following content in the mcp/.env and define your values:
```
ISSUER_URL=https://your-domain.auth0.com/
AUDIENCE=https://your-api-identifier
SECRET_KEY=your-client-secret  # Or fetch JWKS for RS256
```
# Work in progress..
Need to complete the docker implementation and ssl support
# Installation
```
git clone https://github.com/format37/mcp-weather.git
cd mcp-weather
./compose.sh
```