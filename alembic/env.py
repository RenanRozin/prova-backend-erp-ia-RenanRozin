"""Ambiente do Alembic em modo assíncrono.

Roda sobre o mesmo engine asyncpg da aplicação, em vez de exigir um driver
síncrono só para migrar. Menos uma dependência e um DSN a menos para divergir.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.db import Base

# Importar o pacote de modelos é o que popula Base.metadata. Sem esta linha o
# autogenerate acha que o banco deve ficar vazio e gera migração de drop.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar — útil para revisão de DBA antes de aplicar."""
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # compare_type detecta mudança de tipo de coluna; sem isso, alterar
        # Numeric(10,2) para Numeric(12,2) passa despercebido no autogenerate.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
