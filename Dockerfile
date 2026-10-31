FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM python:3.12.13-slim-trixie AS builder
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12.13-slim-trixie
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data/uploads \
    && chown app:app /data/uploads
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "docparser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
