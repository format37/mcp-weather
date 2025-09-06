FROM python:3.11

WORKDIR /app
COPY mcp_server.py /app/
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# CMD ["python", "mcp_server.py"]
CMD ["uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "443", "--ssl-keyfile", "/path/to/privkey.pem", "--ssl-certfile", "/path/to/fullchain.pem"]
