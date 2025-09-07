sudo docker rm -f mcp-weather-resource-server || true
sudo docker rm -f mcp-weather-negative-image-server || true
sudo docker rm -f mcp-weather-caddy || true
# Build
sudo docker compose build
sudo docker compose up --force-recreate -d
