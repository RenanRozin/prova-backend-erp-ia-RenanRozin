"""Orquestração do agente: planejar, executar e narrar o resultado.

O fluxo é o mesmo de um agente com LLM real — só a etapa de planejamento é que
hoje não usa modelo:

    pergunta -> [planner] -> interpretacao -> [guardrails] -> [ferramenta] -> resposta

A narração em linguagem natural aqui é feita por templates. Num agente com LLM,
seria o próprio modelo redigindo a partir do resultado da ferramenta. A diferença
importa menos do que parece: em ambos os casos, **o número exibido vem do banco,
nunca do gerador de texto**. É essa separação que impede o sistema de alucinar
saldo de estoque — o modelo escolhe a pergunta a fazer ao banco, não a resposta.
"""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.executor import Executor
from app.agent.planner import Planner, planner_padrao, sugestoes_de_uso
from app.agent.schemas import PassoDaTrilha, Pergunta, RespostaDoAgente

logger = logging.getLogger(__name__)


class AgenteERP:
    def __init__(self, session: AsyncSession, planner: Planner | None = None) -> None:
        self.session = session
        self.planner = planner or planner_padrao()
        self.executor = Executor(session)

    async def responder(self, pergunta: Pergunta) -> RespostaDoAgente:
        inicio = time.perf_counter()

        interpretacao = await self.planner.planejar(pergunta.texto)
        resultado = await self.executor.executar(interpretacao, confirmado=pergunta.confirmar)

        trilha: list[PassoDaTrilha] = [
            PassoDaTrilha(
                etapa="normalizacao",
                detalhe=f"estrategia={interpretacao.estrategia}",
            ),
            *resultado.trilha,
        ]
        trilha.append(
            PassoDaTrilha(
                etapa="total",
                detalhe="tempo de processamento",
                duracao_ms=round((time.perf_counter() - inicio) * 1000, 2),
            )
        )

        # Log com a interpretação inteira: é o equivalente ao logging de prompt e
        # resposta discutido na Questao 9, e o que permite auditar depois por que
        # o agente fez o que fez.
        logger.info(
            "pergunta processada pelo agente",
            extra={
                "context": {
                    "pergunta": pergunta.texto,
                    "ferramenta": interpretacao.ferramenta,
                    "argumentos": interpretacao.argumentos,
                    "confianca": interpretacao.confianca,
                    "status": resultado.status,
                }
            },
        )

        return RespostaDoAgente(
            pergunta=pergunta.texto,
            status=resultado.status,
            resposta=self._narrar(resultado.status, interpretacao.ferramenta, resultado),
            interpretacao=interpretacao,
            dados=resultado.dados,
            trilha=trilha,
            sugestoes=sugestoes_de_uso() if resultado.status == "nao_compreendido" else [],
        )

    # ------------------------------------------------------------------ narração

    def _narrar(self, status: str, ferramenta: str | None, resultado) -> str:
        if status == "nao_compreendido":
            return (
                "Nao consegui interpretar a pergunta com seguranca suficiente para consultar "
                "os dados. Reformule ou use um dos exemplos sugeridos."
            )

        if status == "confirmacao_necessaria":
            args = resultado.dados["argumentos"]
            return (
                f"Esta acao e destrutiva e nao foi executada. Para confirmar a remocao do "
                f"produto {args.get('produto_id')}, repita a pergunta com confirmar=true."
            )

        if status == "erro_na_ferramenta":
            return resultado.mensagem or "Nao foi possivel concluir a consulta."

        return self._narrar_sucesso(ferramenta, resultado.dados)

    @staticmethod
    def _narrar_sucesso(ferramenta: str | None, dados) -> str:
        if ferramenta == "consultar_estoque_baixo":
            total = dados["total"]
            limite = dados["limite"]
            if total == 0:
                return f"Nenhum produto esta com estoque igual ou abaixo de {limite} unidades."
            nomes = ", ".join(
                f"{p['nome']} ({p['quantidade_em_estoque']})" for p in dados["produtos"][:5]
            )
            sufixo = "" if total <= 5 else f" e outros {total - 5}"
            plural = "produto esta" if total == 1 else "produtos estao"
            return f"{total} {plural} com estoque ate {limite} unidades: {nomes}{sufixo}."

        if ferramenta == "buscar_produtos":
            total = dados["total"]
            if total == 0:
                return "Nenhum produto atende aos criterios informados."
            nomes = ", ".join(f"{p['nome']} (R$ {p['preco']})" for p in dados["produtos"][:5])
            sufixo = "" if total <= 5 else f" e outros {total - 5}"
            return f"Encontrei {total} produto(s): {nomes}{sufixo}."

        if ferramenta == "resumo_do_estoque":
            return (
                f"Ha {dados['total_produtos']} produtos cadastrados, somando "
                f"{dados['total_unidades']} unidades e R$ {dados['valor_total_estoque']} "
                f"em valor de estoque."
            )

        if ferramenta == "detalhar_produto":
            if not dados["encontrado"]:
                return f"Nao existe produto com o id {dados['produto_id']}."
            p = dados["produto"]
            return (
                f"{p['nome']}: R$ {p['preco']}, {p['quantidade_em_estoque']} unidades em estoque."
            )

        if ferramenta == "remover_produto":
            if not dados["removido"]:
                return f"Nada foi removido: {dados['motivo']}."
            return f"Produto {dados['produto_id']} ({dados['nome']}) removido do cadastro."

        return "Consulta concluida."
