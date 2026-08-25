"""Contrato da visão agregada (Parte 2, Questão 4)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FonteResposta(BaseModel):
    """O que veio (ou não veio) de cada serviço consultado.

    O status por fonte é o que transforma "deu erro" em informação útil: o
    cliente da API sabe exatamente qual pedaço faltou e pode decidir se
    renderiza a tela mesmo assim.
    """

    status: str = Field(description="ok | indisponivel | invalido")
    dados: dict[str, Any] | None = None
    erro: str | None = None
    tentativas: int
    latencia_ms: float


class VisaoAgregada(BaseModel):
    cliente_id: int
    produto_id: int
    gerado_em: datetime
    completo: bool = Field(description="False quando alguma fonte falhou")
    duracao_total_ms: float
    fontes: dict[str, FonteResposta]
