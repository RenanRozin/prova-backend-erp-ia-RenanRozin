"""Schemas genéricos reaproveitados pelos routers."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope de paginação.

    Devolver `items` + metadados em vez de uma lista crua é o que permite ao
    cliente montar paginador sem adivinhar. `total` custa um COUNT a mais — vale
    a pena aqui; num volume muito maior a alternativa seria keyset pagination
    (cursor), que não degrada com offset alto.
    """

    items: list[T]
    total: int = Field(description="Total de registros que casam com o filtro")
    limit: int
    offset: int

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.items) < self.total
