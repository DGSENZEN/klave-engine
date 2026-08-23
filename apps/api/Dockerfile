# Klave Engine API — CPU-only, with LibreDWG's dwg2dxf for DWG uploads.
# Build from the repo root:  docker build -f apps/api/Dockerfile .
# GNU LibreDWG is not packaged by Debian, so dwg2dxf is built from the
# release tarball: statically linked, one binary to copy.
FROM debian:trixie-slim AS libredwg
ARG LIBREDWG_VERSION=0.13.3
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates xz-utils python3 \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/libredwg.tar.xz \
        https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/libredwg-${LIBREDWG_VERSION}.tar.xz \
    && mkdir /tmp/libredwg && tar -xJf /tmp/libredwg.tar.xz -C /tmp/libredwg --strip-components=1 \
    && cd /tmp/libredwg \
    && ./configure --disable-shared --disable-bindings --disable-docs --disable-werror --program-prefix= \
    && make -j"$(nproc)" \
    && install -s programs/dwg2dxf /usr/local/bin/dwg2dxf \
    && /usr/local/bin/dwg2dxf --version

FROM python:3.12-slim-trixie

# dwg2dxf converts DWG uploads; DXF-only projects work without it, and the
# API reports honestly when a DWG cannot be converted. curl serves the
# container healthcheck.
COPY --from=libredwg /usr/local/bin/dwg2dxf /usr/local/bin/dwg2dxf
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
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
