# syntax=docker/dockerfile:1

# ---------- Stage 1: build dependencies into a virtualenv ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only requirements first so this layer is cached until deps change
COPY requirements.txt .
RUN pip install -r requirements.txt


# ---------- Stage 2: slim runtime image ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./

USER app

EXPOSE 8000

# python:slim has no curl, so use the stdlib for the health probe
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

# Single worker on purpose: APScheduler runs inside the app process,
# so multiple workers would fire every scheduled job multiple times.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]