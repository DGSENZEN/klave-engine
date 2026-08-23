# Klave Engine API — CPU-only, with LibreDWG's dwg2dxf for DWG uploads.
# Build from the repo root:  docker build -f apps/api/Dockerfile .
FROM python:3.12-slim-bookworm

# dwg2dxf (GNU LibreDWG) converts DWG uploads; DXF-only projects work
# without it, and the API reports honestly when a DWG cannot be converted.
# curl serves the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libredwg-tools curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/__init__.py ./apps/__init__.py
RUN uv sync --frozen --no-dev

ENV KLAVE_DATA_DIR=/data \
    KLAVE_REPORTS_DIR=/data/reports \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# --proxy-headers: Caddy terminates TLS in front; the API must see https.
CMD [".venv/bin/uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
