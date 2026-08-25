"""Produto — a entidade central da Parte 3."""

from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # Numeric, nunca float: dinheiro em ponto flutuante gera divergência de
    # centavos que só aparece no fechamento contábil, quando já é tarde.
    preco: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantidade_em_estoque: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # As mesmas regras do Pydantic, repetidas no banco. Validação de aplicação
        # protege do usuário; constraint protege do script de importação, do
        # migration mal escrito e do estagiário com acesso ao psql.
        CheckConstraint("preco >= 0", name="ck_produtos_preco_nao_negativo"),
        CheckConstraint("quantidade_em_estoque >= 0", name="ck_produtos_estoque_nao_negativo"),
        # Índice para o filtro "estoque baixo", que é a consulta mais quente do
        # domínio (dashboard, alerta e o agente da Parte 5 usam os três).
        Index("ix_produtos_estoque", "quantidade_em_estoque"),
    )
