sudo docker rm -f mcp-weather-resource-server || true
sudo docker rm -f mcp-weather-auth-server || true
# Build
sudo docker compose build
sudo docker compose up --force-recreate
