# syntax=docker/dockerfile:1.7
# Multi-stage build for agno-dcp-demo.
#
#   Stage 1 (builder): install dependencies into a virtualenv inside
#   /opt/venv, using uv for speed.
#   Stage 2 (runtime): copy /opt/venv + the application source onto a
#   slim Python image, drop privileges, expose 8000.
#
# The persistent volume mount path is /app/data, matching fly.toml.

# ─── Builder ───────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast resolver); falls back to pip if uv isn't reachable.
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .

# ─── Runtime ────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Non-root user for runtime safety
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home --shell /sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app /app/app
COPY pyproject.toml README.md /app/

# Persistent volume mount target
RUN mkdir -p /app/data && chown -R app:app /app

USER app

ENV DCP_DB_PATH=/app/data/agent.db \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
