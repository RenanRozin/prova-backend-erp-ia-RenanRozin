"""Ponto de entrada da API.

O app é montado por uma factory (create_app) em vez de um módulo com estado
global: assim cada teste instancia uma aplicação limpa, com overrides de
dependência próprios, sem contaminar os demais.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.logging import setup_logging
from app.core.redis_client import close_redis, get_redis
from app.routers import auth, products
from app.workers.queue import fechar_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info(
        "aplicação iniciando",
        extra={"context": {"env": settings.environment, "app": settings.app_name}},
    )

    yield

    # Encerramento explícito: sem isso o processo pode morrer com conexões
    # penduradas no Postgres e no Redis até o timeout do servidor.
    await fechar_pool()
    await close_redis()
    await engine.dispose()
    logger.info("aplicação encerrada")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Prova prática Back-end: módulo de Produtos e Estoque de um ERP, "
            "com consulta agregada assíncrona e um agente de linguagem natural "
            "sem dependência de LLM externo."
        ),
        lifespan=lifespan,
    )

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def liveness() -> dict[str, str]:
        """Diz apenas se o processo está de pé, sem tocar em dependência externa.

        Um liveness que consulta o banco faz o orquestrador matar a API quando
        quem caiu foi o banco — e reiniciar a API não conserta banco nenhum.
        """
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    async def readiness(response: Response) -> JSONResponse:
        """Diz se dá para servir tráfego: precisa de Postgres e Redis vivos.

        É este o probe que tira a instância do balanceador. Responde 503 quando
        degradado — readiness que devolve 200 sempre não serve para nada.
        """
        checks: dict[str, str] = {}

        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:  # noqa: BLE001 — o probe reporta, não trata
            checks["postgres"] = f"erro: {exc.__class__.__name__}"

        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"erro: {exc.__class__.__name__}"

        saudavel = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if saudavel else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ok" if saudavel else "degradado", "checks": checks},
        )

    app.include_router(auth.router)
    app.include_router(products.router)

    return app


app = create_app()
