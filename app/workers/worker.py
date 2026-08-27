"""Consumidor da fila (arq).

Sobe como processo separado no compose. Separar API de worker não é capricho de
arquitetura: são perfis de recurso e de escala diferentes — a API escala por
requisição/segundo, o worker por profundidade de fila — e uma tarefa pesada num
processo compartilhado rouba o event loop de quem está esperando resposta HTTP.
"""

import logging

from arq import cron
from sqlalchemy import select

from app.core.db import SessionLocal, engine
from app.core.logging import setup_logging
from app.models.product import Product
from app.models.stock_alert import StockAlert
from app.workers.queue import redis_settings

logger = logging.getLogger(__name__)

LIMITE_PADRAO = 10


async def registrar_alerta_estoque_baixo(ctx: dict, produto_id: int, limite: int) -> dict:
    """Grava um alerta se o produto continuar abaixo do limite.

    A tarefa relê o produto do banco em vez de confiar no valor que veio no
    payload: entre o enfileiramento e a execução pode ter entrado uma reposição,
    e alertar sobre um estoque que já foi corrigido é ruído que treina o operador
    a ignorar alerta.

    É idempotente por releitura — reprocessar o mesmo job não muda a conclusão.
    """
    async with SessionLocal() as session:
        produto = await session.get(Product, produto_id)

        if produto is None:
            logger.warning(
                "produto sumiu antes do processamento",
                extra={"context": {"produto_id": produto_id}},
            )
            return {"status": "produto_inexistente", "produto_id": produto_id}

        if produto.quantidade_em_estoque > limite:
            return {"status": "estoque_regularizado", "produto_id": produto_id}

        session.add(
            StockAlert(
                produto_id=produto.id,
                produto_nome=produto.nome,
                quantidade_no_momento=produto.quantidade_em_estoque,
                limite_configurado=limite,
                origem="evento",
            )
        )
        await session.commit()

    logger.info(
        "alerta de estoque baixo registrado",
        extra={"context": {"produto_id": produto_id, "limite": limite}},
    )
    return {"status": "alerta_registrado", "produto_id": produto_id}


async def varredura_estoque_baixo(ctx: dict) -> dict:
    """Varredura periódica — a rede de segurança do alerta por evento.

    Alerta disparado só por evento perde o produto que ficou parado abaixo do
    limite sem sofrer nenhuma escrita. A varredura fecha esse buraco.
    """
    async with SessionLocal() as session:
        stmt = select(Product).where(Product.quantidade_em_estoque <= LIMITE_PADRAO)
        produtos = list((await session.execute(stmt)).scalars().all())

        for produto in produtos:
            session.add(
                StockAlert(
                    produto_id=produto.id,
                    produto_nome=produto.nome,
                    quantidade_no_momento=produto.quantidade_em_estoque,
                    limite_configurado=LIMITE_PADRAO,
                    origem="varredura",
                )
            )
        await session.commit()

    logger.info("varredura concluída", extra={"context": {"produtos": len(produtos)}})
    return {"status": "ok", "produtos_alertados": len(produtos)}


async def startup(ctx: dict) -> None:
    setup_logging()
    logger.info("worker iniciado")


async def shutdown(ctx: dict) -> None:
    await engine.dispose()
    logger.info("worker encerrado")


class WorkerSettings:
    """Configuração lida pelo comando `arq app.workers.worker.WorkerSettings`."""

    functions = [registrar_alerta_estoque_baixo]
    cron_jobs = [cron(varredura_estoque_baixo, minute={0, 30}, run_at_startup=False)]

    on_startup = startup
    on_shutdown = shutdown

    # Atributo, não método: o arq lê isto direto da classe ao subir.
    redis_settings = redis_settings()

    # 3 tentativas com backoff do próprio arq. Acima disso o job vai para a lista
    # de falhas em vez de ficar em loop consumindo worker.
    # O arq grava uma chave de saude no Redis neste intervalo; e ela que o
    # healthcheck do compose consulta com a flag --check.
    health_check_interval = 30

    max_tries = 3
    job_timeout = 30
    keep_result = 3600
