# mcp-weather
A simple weather MCP example using Docker and Python.

- Input: lat, lon
- Output: temperature

## Reverse Proxy Setup

This repo now runs behind a reverse proxy (Caddy) that terminates TLS on port 443 and routes subpaths to internal services. The weather MCP runs over HTTP internally on port `8001` and is exposed at:

- `https://rtlm.info/weather/` → weather MCP

TLS certificates are handled entirely by Caddy; the app no longer mounts certs or binds to `:443` directly.

## Installation
```
git clone https://github.com/format37/mcp-weather.git
cd mcp-weather
./compose.sh
```

To view logs:
```
sudo docker logs -f mcp-gateway   # Caddy (reverse proxy)
sudo docker logs -f mcp-weather-resource-server   # Weather MCP
```

## Notes

- The app still supports HTTPS if certs are provided, but in this setup HTTPS is handled by Caddy.
- A future MCP (e.g., image-negative) can be added at another subpath via the Caddyfile.
