"""Alerta de estoque baixo, gravado pelo worker da fila (Parte 3)."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin


class StockAlert(Base, TimestampMixin):
    __tablename__ = "alertas_estoque"

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(
        ForeignKey("produtos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    produto_nome: Mapped[str] = mapped_column(String(120), nullable=False)
    quantidade_no_momento: Mapped[int] = mapped_column(Integer, nullable=False)
    limite_configurado: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(String(30), nullable=False, default="worker")
