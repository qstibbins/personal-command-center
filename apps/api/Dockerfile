# syntax=docker/dockerfile:1
# Production FastAPI image for Render private service (ADR 0004).
# Reproducible install via uv.lock; non-root runtime; no secrets baked in.

FROM python:3.12-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

# Install production dependencies only into /.venv (locked).
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=10000

RUN groupadd --system --gid 10001 pcc \
    && useradd --system --uid 10001 --gid pcc --home /app --shell /usr/sbin/nologin pcc

WORKDIR /app

COPY --from=builder --chown=pcc:pcc /app/.venv /app/.venv
COPY --from=builder --chown=pcc:pcc /app/src /app/src
COPY --from=builder --chown=pcc:pcc /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=pcc:pcc /app/migrations /app/migrations
COPY --from=builder --chown=pcc:pcc /app/pyproject.toml /app/pyproject.toml

USER pcc

EXPOSE 10000

# Bind 0.0.0.0 for Render private networking (not 127.0.0.1).
# PORT is injected by Render (default 10000 for private services).
CMD ["sh", "-c", "exec uvicorn pcc.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
