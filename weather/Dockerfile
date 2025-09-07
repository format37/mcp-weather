FROM python:3.11

WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py /app/
COPY requirements.txt /app/

CMD ["python", "server.py"]
