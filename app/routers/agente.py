"""Endpoints do agente de linguagem natural (Parte 5)."""

from typing import Any

from fastapi import APIRouter

from app.agent.orchestrator import AgenteERP
from app.agent.schemas import Pergunta, RespostaDoAgente
from app.agent.tools import REGISTRO, esquema_function_calling, esquema_mcp
from app.routers.deps import SessionDep

router = APIRouter(prefix="/agente", tags=["agente"])


@router.post(
    "/perguntar",
    response_model=RespostaDoAgente,
    summary="Responde uma pergunta em linguagem natural sobre os dados do ERP",
)
async def perguntar(pergunta: Pergunta, session: SessionDep) -> RespostaDoAgente:
    """Recebe texto livre, traduz em chamada de ferramenta e devolve JSON.

    Sem nenhuma chamada a provedor externo de IA: a interpretação é feita por um
    planner determinístico, plugável, descrito em app.agent.planner.
    """
    return await AgenteERP(session).responder(pergunta)


@router.get(
    "/ferramentas",
    summary="Lista as ferramentas expostas ao agente, nos formatos de LLM e MCP",
)
async def listar_ferramentas() -> dict[str, Any]:
    """Publica o contrato das ferramentas.

    O endpoint existe para tornar concreto o argumento da Questão 9: as mesmas
    capacidades já saem daqui prontas tanto para o function calling de um
    provedor de LLM quanto para o tools/list de um servidor MCP. É o que torna a
    troca do planner uma mudança local, e não uma reescrita.
    """
    return {
        "total": len(REGISTRO),
        "function_calling": esquema_function_calling(),
        "mcp": esquema_mcp(),
    }
