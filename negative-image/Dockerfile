FROM python:3.11

WORKDIR /app
COPY server.py /app/
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "server.py"]
