"""Colunas repetidas em vários modelos."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Carimbos de criação e atualização.

    Os defaults são do **banco** (`func.now()`, `onupdate`) e não do Python: assim
    um UPDATE feito por migração, script ou outro serviço também atualiza a data.
    Se dependesse do ORM, qualquer escrita fora dele deixaria o dado mentindo.
    """

    data_criacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    data_atualizacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
