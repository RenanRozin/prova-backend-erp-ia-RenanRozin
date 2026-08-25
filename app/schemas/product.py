"""Contratos de entrada e saída de Produto.

Schemas separados por operação (Create / Update / Read) em vez de um modelo único:
o cliente não pode enviar `id` nem `data_criacao`, e no PATCH todo campo é
opcional. Um schema só para os três casos obriga a validar na mão o que o
Pydantic faria de graça.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.validators import validar_nome_produto

# Dinheiro: no máximo 12 dígitos com 2 casas, nunca negativo — o mesmo contrato
# da coluna Numeric(12, 2) e da CHECK constraint no banco.
Preco = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Estoque = Annotated[int, Field(ge=0)]
Nome = Annotated[str, Field(min_length=2, max_length=120)]


class ProductCreate(BaseModel):
    nome: Nome
    preco: Preco
    quantidade_em_estoque: Estoque = 0

    @field_validator("nome")
    @classmethod
    def _valida_nome(cls, v: str) -> str:
        return validar_nome_produto(v)


class ProductUpdate(BaseModel):
    """PATCH: todos os campos opcionais. Ausente significa "não mexer" — por isso
    o service aplica com `exclude_unset=True`."""

    nome: Nome | None = None
    preco: Preco | None = None
    quantidade_em_estoque: Estoque | None = None

    @field_validator("nome")
    @classmethod
    def _valida_nome(cls, v: str | None) -> str | None:
        # None aqui é "campo não enviado", não "nome inválido".
        return validar_nome_produto(v) if v is not None else None

    @model_validator(mode="after")
    def _exige_ao_menos_um_campo(self) -> "ProductUpdate":
        if not self.model_fields_set:
            raise ValueError("informe ao menos um campo para atualizar")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    preco: Decimal
    quantidade_em_estoque: int
    data_criacao: datetime
    data_atualizacao: datetime


class ProductFilter(BaseModel):
    """Filtros da listagem. Entra no router via `Depends()`, o que mantém a
    assinatura do endpoint curta e deixa os filtros testáveis isoladamente."""

    nome: str | None = Field(default=None, description="Busca parcial, sem diferenciar maiúsculas")
    preco_min: Decimal | None = Field(default=None, ge=0)
    preco_max: Decimal | None = Field(default=None, ge=0)
    estoque_baixo_ate: int | None = Field(
        default=None, ge=0, description="Apenas produtos com estoque <= este valor"
    )
    ordenar_por: str = Field(default="id", pattern="^(id|nome|preco|quantidade_em_estoque)$")
    ordem: str = Field(default="asc", pattern="^(asc|desc)$")

    @model_validator(mode="after")
    def _faixa_de_preco_coerente(self) -> "ProductFilter":
        if self.preco_min is not None and self.preco_max is not None:
            if self.preco_min > self.preco_max:
                raise ValueError("preco_min não pode ser maior que preco_max")
        return self
