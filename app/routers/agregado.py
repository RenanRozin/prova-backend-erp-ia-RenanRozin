"""Consulta agregada a três serviços em paralelo (Parte 2, Questão 4).

Demonstra o padrão que sustenta qualquer tela de ERP que junta dados de vários
microsserviços: paralelizar, limitar o tempo de cada um e responder com o que
chegou.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.resiliencia import Resultado, com_resiliencia
from app.schemas.agregado import FonteResposta, VisaoAgregada
from app.services.integracoes import (
    SimulacaoDeFalha,
    consultar_cliente,
    consultar_estoque,
    consultar_financeiro,
)

router = APIRouter(prefix="/agregado", tags=["consulta agregada"])

TIMEOUT_PADRAO = 0.5
TENTATIVAS_PADRAO = 3
# Teto de tempo da requisição inteira. Vem antes do produto de timeout por
# tentativas: e o que a API promete a quem consome, e a promessa nao pode
# depender de quantas retentativas aconteceram por dentro.
ORCAMENTO_PADRAO = 1.0


@router.get(
    "/visao-360",
    response_model=VisaoAgregada,
    summary="Consulta estoque, financeiro e cliente em paralelo",
)
async def visao_360(
    cliente_id: Annotated[int, Query(ge=1)] = 1,
    produto_id: Annotated[int, Query(ge=1)] = 1,
    timeout: Annotated[  # noqa: ASYNC109 — parametro de query da API, nao prazo interno
        float, Query(gt=0, le=5, description="Timeout por tentativa, em segundos")
    ] = TIMEOUT_PADRAO,
    tentativas: Annotated[int, Query(ge=1, le=5)] = TENTATIVAS_PADRAO,
    orcamento: Annotated[
        float, Query(gt=0, le=10, description="Teto de tempo por fonte, retries incluidos")
    ] = ORCAMENTO_PADRAO,
    indisponivel: Annotated[
        list[str] | None, Query(description="Fontes que devem responder 503")
    ] = None,
    lenta: Annotated[
        list[str] | None, Query(description="Fontes que devem estourar o timeout")
    ] = None,
    invalida: Annotated[
        list[str] | None, Query(description="Fontes que devem falhar sem retry (4xx)")
    ] = None,
    falha_transitoria: Annotated[
        list[str] | None,
        Query(description="Fontes que falham uma vez e funcionam na retentativa"),
    ] = None,
) -> VisaoAgregada:
    """Três chamadas simultâneas, cada uma com seu próprio timeout e retry.

    **Por que `gather` e não três `await` em sequência:** sequencial, o tempo é a
    soma das latências; em paralelo, é o máximo entre elas. Com as latências
    simuladas aqui, a diferença é ~0,5s contra ~0,35s — e cresce a cada nova
    fonte adicionada à tela.

    **Por que ninguém derruba a resposta inteira:** `com_resiliencia` captura a
    falha e devolve um `Resultado`. Como nenhuma corrotina levanta exceção, o
    `gather` sempre completa. Usar `return_exceptions=True` resolveria metade do
    problema, mas deixaria o tratamento de erro espalhado no endpoint em vez de
    concentrado na política.

    **Timeout por tentativa e orçamento total:** cada tentativa tem seu limite,
    mas a fonte inteira tem um teto (`orcamento`). Sem o teto, 3 tentativas de
    0,5s fariam o usuário esperar 1,5s — o retry viraria a causa da lentidão que
    deveria proteger.

    **Degradação graciosa:** a resposta é 200 com `completo: false` e o motivo
    por fonte. Poderia ser 206/207, mas na prática o cliente HTTP trata qualquer
    coisa fora de 2xx como erro e joga a resposta parcial fora — perdendo os
    dados que chegaram. A informação de completude vai no corpo, onde é usada.
    """
    simulacao = SimulacaoDeFalha(
        indisponiveis=set(indisponivel or []),
        lentas=set(lenta or []),
        invalidas=set(invalida or []),
        # Uma falha antes de funcionar: o suficiente para o retry se provar.
        falhas_transitorias={fonte: 1 for fonte in (falha_transitoria or [])},
    )

    inicio = time.perf_counter()

    resultados: list[Resultado] = await asyncio.gather(
        com_resiliencia(
            "estoque",
            lambda: consultar_estoque(produto_id, simulacao),
            timeout=timeout,
            tentativas=tentativas,
            orcamento_total=orcamento,
        ),
        com_resiliencia(
            "financeiro",
            lambda: consultar_financeiro(cliente_id, simulacao),
            timeout=timeout,
            tentativas=tentativas,
            orcamento_total=orcamento,
        ),
        com_resiliencia(
            "cliente",
            lambda: consultar_cliente(cliente_id, simulacao),
            timeout=timeout,
            tentativas=tentativas,
            orcamento_total=orcamento,
        ),
    )

    duracao = (time.perf_counter() - inicio) * 1000

    return VisaoAgregada(
        cliente_id=cliente_id,
        produto_id=produto_id,
        gerado_em=datetime.now(UTC),
        completo=all(r.sucesso for r in resultados),
        duracao_total_ms=round(duracao, 2),
        fontes={
            r.fonte: FonteResposta(
                status=r.status,
                dados=r.dados,
                erro=r.erro,
                tentativas=r.tentativas,
                latencia_ms=round(r.latencia_ms, 2),
            )
            for r in resultados
        },
    )
