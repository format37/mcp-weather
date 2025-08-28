FROM python:3.11

WORKDIR /app
COPY mcp_server.py /app/
COPY requirements.txt /app/
COPY .env /app/
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8000"]
