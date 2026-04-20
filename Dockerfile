FROM python:3.11-slim

WORKDIR /app

COPY server.py ./
COPY public/ ./public/

RUN pip install --no-cache-dir pywebpush

EXPOSE 8080

CMD ["python3", "server.py"]
