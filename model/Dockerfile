FROM python:3.11-slim

WORKDIR /app

# onnxruntime / chromadb 需要基础编译工具链之外的运行库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -sf http://localhost:8000/admin/report_modes || exit 1

CMD ["python", "-m", "app.main"]
