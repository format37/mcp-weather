sudo docker rm -f mcp-weather-server || true
# Build
sudo docker compose build
sudo docker compose up --force-recreate
