# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder: compila as dependências num virtualenv isolado.
# O compilador C (asyncpg, bcrypt) só existe aqui e não vai para a imagem final.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# requirements copiado sozinho e antes do código: enquanto as dependências não
# mudarem, o cache do Docker reaproveita esta camada e o build leva segundos.
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 — runtime: só o venv pronto + o código. Sem toolchain, imagem menor
# e com menos superfície de ataque.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Usuário sem privilégios: container que roda como root é root no host se
# escapar do namespace.
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

RUN chmod +x /app/scripts/entrypoint.sh

USER app

EXPOSE 8000

# Healthcheck bate no liveness. Usa urllib do próprio Python para não precisar
# instalar curl só para isso.
HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
