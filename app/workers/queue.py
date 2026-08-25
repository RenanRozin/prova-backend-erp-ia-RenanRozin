"""Produção de tarefas para a fila.

## Por que arq e não Celery

O Celery é o padrão de mercado, mas é síncrono na raiz: dentro de uma aplicação
async ele obriga a jogar o enfileiramento para um thread pool ou a manter um
segundo cliente Redis bloqueante. O arq nasceu assíncrono, usa o mesmo
redis-py que a API já usa e o retry/timeout é declarativo.

A troca é consciente: abre-se mão do ecossistema do Celery (flower, rotas
complexas, backends variados) em favor de coerência com a stack. Num cenário com
muitos tipos de tarefa, DAG entre elas e times diferentes consumindo, o Celery —
ou um broker de verdade, como RabbitMQ ou SQS — passaria a valer mais a pena.
"""

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_pool() -> ArqRedis:
    """Pool preguiçoso e único por processo."""
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def fechar_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enfileirar(tarefa: str, **kwargs: Any) -> str | None:
    """Publica uma tarefa e devolve o id do job.

    Falha ao enfileirar NÃO derruba a operação de negócio que já foi confirmada
    no banco: o produto foi salvo, o alerta é acessório. O erro vai para o log
    com contexto suficiente para reprocessar.

    Num sistema onde a tarefa é essencial (nota fiscal, cobrança), esta escolha
    estaria errada — o certo ali é o padrão transactional outbox: grava a
    intenção na mesma transação do dado e um publicador separado entrega.
    """
    try:
        pool = await get_pool()
        job = await pool.enqueue_job(tarefa, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception(
            "falha ao enfileirar tarefa",
            extra={"context": {"tarefa": tarefa, "kwargs": kwargs}},
        )
        return None

    job_id = job.job_id if job else None
    logger.info(
        "tarefa enfileirada",
        extra={"context": {"tarefa": tarefa, "job_id": job_id, "kwargs": kwargs}},
    )
    return job_id
