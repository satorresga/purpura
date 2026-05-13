# ============================================================
# STAGE 1 — Builder: instala dependencias con uv
# ============================================================
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY app/ ./app/

# tests/__init__.py satisface a hatchling (packages=["app","tests"] en pyproject)
# sin meter el script E2E ni screenshots en la imagen de producción.
RUN mkdir -p tests && touch tests/__init__.py

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

RUN uv sync --frozen --no-dev

# ============================================================
# STAGE 2 — Runtime: solo lo necesario
# ============================================================
FROM python:3.12-slim AS runtime

RUN groupadd -r purpura && useradd -r -g purpura -d /app -s /sbin/nologin purpura

WORKDIR /app

COPY --from=builder --chown=purpura:purpura /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER purpura
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
