# syntax=docker/dockerfile:1.7
#
# Two-stage build:
#   1. ``builder`` installs dependencies into a virtualenv-style
#      directory so the runtime image only carries site-packages and
#      application source — not tests, fixtures, migrations env vars,
#      or build caches.
#   2. ``runtime`` uses python:3.13-slim, copies the prepared venv and
#      source, and runs as a non-root user.
#
# Trivy scan command (NOT RUN HERE — Trivy not installed in this env):
#   trivy image --severity HIGH,CRITICAL sams-backend:<tag>
#
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System deps for psycopg wheels. The libpq5 package is the only
# runtime dep that needs to be installed in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=5000 \
    BIND_ADDRESS=0.0.0.0

# libpq5 is required by the psycopg binary driver at runtime. No
# compiler is needed in the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from the builder stage.
COPY --from=builder /install /usr/local

# Copy only what production needs. Tests, fixtures, scripts, and
# .env are explicitly excluded by .dockerignore.
COPY . .

# Create and switch to a non-root runtime user.
RUN useradd -m -r appuser \
    && mkdir -p /data/reports /data/uploads \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/v1/health', timeout=3)" || exit 1

# gunicorn is the production server for Linux containers; the same
# app runs under waitress on Windows hosts (python -m app.runner).
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "--timeout", "120", "run:app"]