"""Cliente Redis compartilhado pelo processo.

Um pool por processo, criado no startup e fechado no shutdown. Criar cliente por
requisição desperdiça handshake e estoura o limite de conexões do Redis sob carga.
"""

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

_settings = get_settings()

_pool = ConnectionPool.from_url(
    _settings.redis_url,
    decode_responses=True,
    max_connections=20,
)


def get_redis() -> Redis:
    """Dependência do FastAPI. O cliente é leve — o que é caro é o pool, e ele é único."""
    return Redis(connection_pool=_pool)


async def close_redis() -> None:
    await _pool.disconnect()
