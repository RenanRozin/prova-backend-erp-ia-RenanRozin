"""Timeout, retry e degradação graciosa para chamadas a serviços externos.

Isolado num módulo próprio porque a política de resiliência é uma decisão de
arquitetura, não um detalhe de cada chamada: espalhar try/except com sleep pelo
código faz cada endpoint envelhecer com uma política diferente.

## As três regras aplicadas aqui

1. **Timeout individual, sempre.** Sem timeout, o `gather` espera pelo mais lento
   e a lentidão de um serviço vira lentidão do sistema inteiro — o modo de falha
   mais comum em arquitetura distribuída.

2. **Retry só no que é transitório.** Repetir um timeout ou um 503 faz sentido;
   repetir um 422 é desperdício, e repetir uma operação de escrita não idempotente
   é como se cria cobrança duplicada.

3. **Backoff exponencial COM jitter.** Sem jitter, todos os clientes que falharam
   juntos voltam juntos e derrubam de novo o serviço que estava se recuperando —
   o efeito manada (thundering herd).
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class FalhaTransitoria(Exception):
    """Erro que vale a pena tentar de novo (indisponibilidade, timeout, 5xx)."""


class FalhaPermanente(Exception):
    """Erro que NÃO deve ser repetido (dado inválido, 4xx, regra de negócio)."""


@dataclass
class Resultado[T]:
    """O que aconteceu com uma das chamadas paralelas.

    O resultado carrega o erro em vez de levantá-lo: é isso que permite ao
    endpoint devolver resposta parcial em vez de estourar tudo por causa de uma
    fonte fora do ar.
    """

    fonte: str
    status: str  # "ok" | "indisponivel" | "invalido"
    dados: T | None = None
    erro: str | None = None
    tentativas: int = 0
    latencia_ms: float = 0.0
    detalhes: dict[str, Any] = field(default_factory=dict)

    @property
    def sucesso(self) -> bool:
        return self.status == "ok"


async def com_resiliencia[T](
    fonte: str,
    operacao: Callable[[], Awaitable[T]],
    *,
    timeout: float = 1.0,  # noqa: ASYNC109 — ver justificativa no corpo
    tentativas: int = 3,
    backoff_base: float = 0.05,
    orcamento_total: float | None = None,
) -> Resultado[T]:
    # ASYNC109 sugere delegar o prazo a quem chama, via asyncio.timeout. Aqui o
    # timeout e parte do contrato de propósito: a politica de resiliencia por
    # fonte pertence a esta funcao, nao a cada chamador.
    """Executa `operacao` com timeout por tentativa e retry com backoff.

    Nunca levanta exceção: devolve sempre um `Resultado`, com sucesso ou com o
    motivo da falha. Quem chama decide o que fazer com a fonte que faltou.

    O `timeout` vale por tentativa e o `orcamento_total` vale para a operação
    inteira, retentativas e backoff incluídos. Os dois juntos são necessários:
    só com timeout por tentativa, 3 tentativas de 0,5s viram 1,5s de espera para
    o usuário — o retry protege contra falha passageira e acaba virando a causa
    da lentidão que deveria evitar. O orçamento é o teto que o chamador promete
    ao cliente da API.
    """
    inicio = time.perf_counter()
    prazo_final = inicio + orcamento_total if orcamento_total is not None else None
    ultimo_erro = "erro desconhecido"

    for tentativa in range(1, tentativas + 1):
        # Cada tentativa recebe o menor entre o timeout dela e o que sobrou do
        # orçamento — nunca ultrapassa a promessa feita a quem chamou.
        limite = timeout
        if prazo_final is not None:
            restante = prazo_final - time.perf_counter()
            if restante <= 0:
                ultimo_erro = f"orcamento de {orcamento_total:.2f}s esgotado"
                break
            limite = min(timeout, restante)

        try:
            dados = await asyncio.wait_for(operacao(), timeout=limite)
        except TimeoutError:
            ultimo_erro = f"timeout apos {limite:.2f}s"
        except FalhaTransitoria as exc:
            ultimo_erro = str(exc)
        except FalhaPermanente as exc:
            # Sai na primeira: repetir não muda o resultado, só gasta tempo do
            # usuário e carga do serviço que já disse não.
            return Resultado(
                fonte=fonte,
                status="invalido",
                erro=str(exc),
                tentativas=tentativa,
                latencia_ms=(time.perf_counter() - inicio) * 1000,
            )
        except asyncio.CancelledError:
            # Cancelamento é do event loop (cliente desistiu, shutdown) e não é
            # falha da dependência: engolir aqui quebraria o encerramento limpo.
            raise
        except Exception as exc:  # noqa: BLE001
            ultimo_erro = f"{exc.__class__.__name__}: {exc}"
        else:
            latencia = (time.perf_counter() - inicio) * 1000
            logger.info(
                "chamada externa concluida",
                extra={
                    "context": {
                        "fonte": fonte,
                        "tentativas": tentativa,
                        "latencia_ms": round(latencia, 2),
                    }
                },
            )
            return Resultado(
                fonte=fonte,
                status="ok",
                dados=dados,
                tentativas=tentativa,
                latencia_ms=latencia,
            )

        if tentativa < tentativas:
            # 2^n com jitter completo: espalha as retentativas no intervalo em vez
            # de sincronizar todos os clientes no mesmo instante.
            espera = random.uniform(0, backoff_base * (2 ** (tentativa - 1)))

            # Não faz sentido dormir para uma tentativa que não caberá no prazo.
            if prazo_final is not None and time.perf_counter() + espera >= prazo_final:
                ultimo_erro = f"{ultimo_erro} (orcamento de {orcamento_total:.2f}s esgotado)"
                break

            logger.warning(
                "tentativa falhou, aguardando para repetir",
                extra={
                    "context": {
                        "fonte": fonte,
                        "tentativa": tentativa,
                        "erro": ultimo_erro,
                        "espera_s": round(espera, 3),
                    }
                },
            )
            await asyncio.sleep(espera)

    latencia = (time.perf_counter() - inicio) * 1000
    logger.error(
        "fonte indisponivel apos todas as tentativas",
        extra={"context": {"fonte": fonte, "tentativas": tentativas, "erro": ultimo_erro}},
    )
    return Resultado(
        fonte=fonte,
        status="indisponivel",
        erro=ultimo_erro,
        tentativas=tentativas,
        latencia_ms=latencia,
    )
