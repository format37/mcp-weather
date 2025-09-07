FROM python:3.11

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_image_utils /app/mcp_image_utils
COPY server.py /app/

CMD ["python", "server.py"]
