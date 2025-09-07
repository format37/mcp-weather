FROM python:3.11

WORKDIR /app
COPY mcp_server.py /app/
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "mcp_server.py"]
