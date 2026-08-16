FROM python:3.12-slim

WORKDIR /app

# chromadb（hnswlib）需要 libgomp1 运行库；curl 供健康检查使用
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -sf http://localhost:8000/admin/report_modes || exit 1

CMD ["python", "-m", "app.main"]
