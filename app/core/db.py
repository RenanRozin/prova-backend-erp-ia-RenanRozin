"""Engine, sessão e Base declarativa do SQLAlchemy (modo assíncrono)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

_settings = get_settings()


class Base(DeclarativeBase):
    """Base declarativa. Todos os modelos herdam daqui para que o Alembic
    enxergue o metadata completo no autogenerate."""


engine = create_async_engine(
    _settings.database_url,
    echo=_settings.sql_echo,
    # pool_pre_ping evita o clássico "server closed the connection unexpectedly"
    # quando o Postgres reinicia ou um firewall derruba conexões ociosas.
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependência do FastAPI: uma sessão por requisição, sempre fechada no fim."""
    async with SessionLocal() as session:
        yield session
