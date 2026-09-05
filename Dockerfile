FROM python:3.14.7-alpine3.23

RUN apk update && apk upgrade --no-cache

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-cache \
    && PIP_ROOT_USER_ACTION=ignore /usr/local/bin/python -m pip uninstall -y pip \
    && rm -f /usr/local/bin/uv

RUN adduser -D -u 10001 -s /sbin/nologin appuser \
    && mkdir -p /home/appuser/.local/share \
    && chown -R appuser:appuser /home/appuser
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)"]

CMD ["tramplin-mcp"]

