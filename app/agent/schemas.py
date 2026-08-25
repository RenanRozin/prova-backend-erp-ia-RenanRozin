"""Contratos do agente (Parte 5)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Pergunta(BaseModel):
    texto: str = Field(min_length=3, max_length=500, description="Pergunta em linguagem natural")
    confirmar: bool = Field(
        default=False,
        description="Confirmação explícita para executar uma ação sensível",
    )


class Interpretacao(BaseModel):
    """Como o agente entendeu a pergunta — o equivalente ao tool call de um LLM."""

    ferramenta: str | None = None
    argumentos: dict[str, Any] = Field(default_factory=dict)
    confianca: float = Field(ge=0, le=1, description="0 a 1")
    estrategia: str = Field(description="Qual planner produziu esta interpretação")
    justificativa: str = Field(description="Por que esta ferramenta foi escolhida")


class PassoDaTrilha(BaseModel):
    """Um evento no processamento. É a matéria-prima da observabilidade descrita
    na Questão 9 — o mesmo formato serve para auditar um agente com LLM real."""

    etapa: str
    detalhe: str
    duracao_ms: float | None = None


class RespostaDoAgente(BaseModel):
    pergunta: str
    status: Literal[
        "respondido",
        "confirmacao_necessaria",
        "nao_compreendido",
        "erro_na_ferramenta",
    ]
    resposta: str = Field(description="Resposta em linguagem natural")
    interpretacao: Interpretacao
    dados: Any | None = Field(default=None, description="Resultado estruturado da ferramenta")
    trilha: list[PassoDaTrilha] = Field(default_factory=list)
    sugestoes: list[str] = Field(
        default_factory=list, description="O que perguntar quando não houve compreensão"
    )
