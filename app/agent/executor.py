"""Execução de ferramentas com validação e guardrails.

## Por que a validação e os guardrails ficam AQUI, e não no planner

Porque o planner é a peça substituível. Hoje ele é um regex disciplinado; amanhã
é um LLM que pode alucinar um nome de ferramenta, inventar um argumento ou
decidir que apagar o cadastro inteiro responde bem à pergunta.

Colocar a defesa no executor significa que ela vale para qualquer planner, atual
ou futuro. É a diferença entre confiar no modelo e projetar para não precisar
confiar nele.

## As quatro barreiras, na ordem em que são aplicadas

1. **Lista fechada de ferramentas.** Só executa o que está no registro. Nunca há
   SQL, eval ou nome de função vindo do texto do usuário — a ferramenta é
   escolhida por chave num dicionário, e o que não está lá não existe.

2. **Limiar de confiança.** Abaixo do limiar o agente diz que não entendeu, em
   vez de agir no chute. Responder errado com convicção é pior que não responder.

3. **Validação por JSON Schema.** Os argumentos passam pelo mesmo schema
   publicado às ferramentas. Argumento inventado, tipo errado ou campo a mais é
   barrado antes de virar consulta.

4. **Confirmação para ação destrutiva.** Ferramenta marcada como destrutiva
   nunca executa na primeira passada: devolve o que pretende fazer e espera
   confirmação humana explícita.
"""

import logging
import time
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import Interpretacao, PassoDaTrilha
from app.agent.tools import REGISTRO, Ferramenta

logger = logging.getLogger(__name__)

# Abaixo disto o agente prefere admitir que não entendeu. O número é uma decisão
# de produto, não técnica: quanto mais caro o erro, mais alto ele deve ser.
LIMIAR_DE_CONFIANCA = 0.6


class ResultadoDaExecucao:
    def __init__(
        self,
        status: str,
        dados: Any | None = None,
        mensagem: str = "",
        trilha: list[PassoDaTrilha] | None = None,
    ) -> None:
        self.status = status
        self.dados = dados
        self.mensagem = mensagem
        self.trilha = trilha or []


class Executor:
    """Aplica as barreiras e executa a ferramenta escolhida."""

    def __init__(self, session: AsyncSession, limiar: float = LIMIAR_DE_CONFIANCA) -> None:
        self.session = session
        self.limiar = limiar

    async def executar(
        self, interpretacao: Interpretacao, confirmado: bool
    ) -> ResultadoDaExecucao:
        trilha: list[PassoDaTrilha] = []

        # Barreira 1 — a ferramenta precisa existir no registro.
        if interpretacao.ferramenta is None:
            trilha.append(
                PassoDaTrilha(etapa="planejamento", detalhe="nenhuma ferramenta correspondente")
            )
            return ResultadoDaExecucao("nao_compreendido", trilha=trilha)

        ferramenta = REGISTRO.get(interpretacao.ferramenta)
        if ferramenta is None:
            # Só acontece com planner defeituoso ou LLM alucinando nome de função.
            logger.warning(
                "ferramenta inexistente solicitada",
                extra={"context": {"ferramenta": interpretacao.ferramenta}},
            )
            trilha.append(
                PassoDaTrilha(
                    etapa="guardrail",
                    detalhe=f"ferramenta {interpretacao.ferramenta!r} nao existe no registro",
                )
            )
            return ResultadoDaExecucao("nao_compreendido", trilha=trilha)

        trilha.append(
            PassoDaTrilha(
                etapa="planejamento",
                detalhe=f"{ferramenta.nome} (confianca {interpretacao.confianca:.2f})",
            )
        )

        # Barreira 2 — confiança mínima.
        if interpretacao.confianca < self.limiar:
            trilha.append(
                PassoDaTrilha(
                    etapa="guardrail",
                    detalhe=(
                        f"confianca {interpretacao.confianca:.2f} "
                        f"abaixo do limiar {self.limiar}"
                    ),
                )
            )
            return ResultadoDaExecucao("nao_compreendido", trilha=trilha)

        # Barreira 3 — os argumentos precisam obedecer ao JSON Schema publicado.
        try:
            self._validar(ferramenta, interpretacao.argumentos)
        except JsonSchemaError as exc:
            trilha.append(
                PassoDaTrilha(etapa="guardrail", detalhe=f"argumentos invalidos: {exc.message}")
            )
            return ResultadoDaExecucao(
                "erro_na_ferramenta",
                mensagem=f"Os argumentos nao passaram na validacao: {exc.message}",
                trilha=trilha,
            )
        trilha.append(PassoDaTrilha(etapa="validacao", detalhe="argumentos aderentes ao schema"))

        # Barreira 4 — ação destrutiva exige confirmação humana.
        if ferramenta.exige_confirmacao and not confirmado:
            trilha.append(
                PassoDaTrilha(etapa="guardrail", detalhe="acao destrutiva aguardando confirmacao")
            )
            return ResultadoDaExecucao(
                "confirmacao_necessaria",
                dados={"acao_pendente": ferramenta.nome, "argumentos": interpretacao.argumentos},
                trilha=trilha,
            )

        inicio = time.perf_counter()
        try:
            dados = await ferramenta.executor(self.session, interpretacao.argumentos)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "falha ao executar ferramenta",
                extra={"context": {"ferramenta": ferramenta.nome}},
            )
            trilha.append(
                PassoDaTrilha(etapa="execucao", detalhe=f"erro: {exc.__class__.__name__}")
            )
            return ResultadoDaExecucao(
                "erro_na_ferramenta",
                mensagem="A ferramenta falhou ao consultar os dados.",
                trilha=trilha,
            )

        duracao = (time.perf_counter() - inicio) * 1000
        trilha.append(
            PassoDaTrilha(etapa="execucao", detalhe=ferramenta.nome, duracao_ms=round(duracao, 2))
        )
        return ResultadoDaExecucao("respondido", dados=dados, trilha=trilha)

    @staticmethod
    def _validar(ferramenta: Ferramenta, argumentos: dict[str, Any]) -> None:
        Draft202012Validator(ferramenta.parametros).validate(argumentos)
