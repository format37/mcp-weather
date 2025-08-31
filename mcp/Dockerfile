FROM python:3.11

WORKDIR /app
COPY mcp_server.py /app/
COPY mcp_simple_auth/ /app/mcp_simple_auth/
COPY requirements.txt /app/
COPY .env /app/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "mcp_server.py"]
