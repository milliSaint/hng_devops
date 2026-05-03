FROM python:3.11-slim-bookworm AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target /install

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import redis,os; redis.Redis(host=os.environ.get('REDIS_HOST','redis'),port=int(os.environ.get('REDIS_PORT',6379)),password=os.environ.get('REDIS_PASSWORD')).ping()"
CMD ["python", "worker.py"]
