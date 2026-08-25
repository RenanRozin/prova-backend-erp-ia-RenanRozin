"""Carga inicial: usuário administrador e um catálogo de exemplo.

Roda no entrypoint do container. É idempotente — subir o compose dez vezes não
duplica nada — porque seed que só funciona no banco vazio quebra exatamente na
segunda vez, quando ninguém está olhando.
"""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.models.product import Product
from app.models.user import User

logger = logging.getLogger(__name__)

# Catálogo pensado para exercitar os filtros e o agente da Parte 5: preços em
# faixas distintas e alguns itens propositalmente abaixo do limite de estoque.
PRODUTOS_EXEMPLO = [
    ("Parafuso sextavado M8", Decimal("0.85"), 1500),
    ("Chapa de aço 2mm", Decimal("189.90"), 42),
    ("Rolamento 6203ZZ", Decimal("24.50"), 8),
    ("Correia dentada A-38", Decimal("67.00"), 3),
    ("Motor trifásico 2CV", Decimal("1890.00"), 5),
    ("Óleo lubrificante ISO 68", Decimal("112.30"), 26),
    ("Sensor indutivo PNP", Decimal("143.75"), 0),
    ("Disco de corte 7 polegadas", Decimal("12.40"), 210),
    ("Luva de segurança tamanho G", Decimal("18.90"), 9),
    ("Inversor de frequência 3CV", Decimal("2450.00"), 2),
]


async def criar_admin(session) -> None:
    settings = get_settings()
    existente = await session.execute(
        select(User).where(User.username == settings.seed_admin_username)
    )
    if existente.scalar_one_or_none():
        logger.info("usuário administrador já existe")
        return

    session.add(
        User(
            username=settings.seed_admin_username,
            hashed_password=hash_password(settings.seed_admin_password.get_secret_value()),
        )
    )
    logger.info(
        "usuário administrador criado",
        extra={"context": {"username": settings.seed_admin_username}},
    )


async def criar_produtos(session) -> None:
    total = (await session.execute(select(func.count(Product.id)))).scalar_one()
    if total:
        logger.info("catálogo já populado", extra={"context": {"produtos": total}})
        return

    for nome, preco, quantidade in PRODUTOS_EXEMPLO:
        session.add(Product(nome=nome, preco=preco, quantidade_em_estoque=quantidade))
    logger.info("catálogo criado", extra={"context": {"produtos": len(PRODUTOS_EXEMPLO)}})


async def main() -> None:
    setup_logging()
    async with SessionLocal() as session:
        await criar_admin(session)
        await criar_produtos(session)
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
