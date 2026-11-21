# Not built or run on the author's machine (no Docker there). CI builds it.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra server
COPY backdate backdate
COPY examples examples
COPY server server
COPY manage.py ./
RUN uv sync --frozen --no-dev --extra server

FROM python:3.13-slim
RUN useradd --system --uid 10001 --no-create-home backdate
WORKDIR /app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    BACKDATE_ENV=production \
    LOG_JSON=true
USER backdate
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz').status != 200)"
CMD ["gunicorn", "server.wsgi", "--bind", "0.0.0.0:8000", "--workers", "4", "--access-logfile", "-"]
