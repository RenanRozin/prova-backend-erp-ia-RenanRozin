"""Interpretação e guardrails do agente (Parte 5).

Nenhum destes testes toca banco ou rede: o planner é uma função pura de texto
para intenção, e os guardrails são decisões tomadas antes de qualquer execução.
Essa testabilidade é consequência direta de separar planejar de executar.
"""

import pytest

from app.agent.executor import Executor
from app.agent.planner import PlannerPorRegras, _para_numero, normalizar
from app.agent.schemas import Interpretacao
from app.agent.tools import REGISTRO, esquema_function_calling, esquema_mcp

planner = PlannerPorRegras()


# ---------------------------------------------------------------- normalização


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Estão ACABANDO", "estao acabando"),
        ("  muitos    espacos  ", "muitos espacos"),
        ("Óleo lubrificante", "oleo lubrificante"),
    ],
)
def test_normalizacao(entrada, esperado):
    assert normalizar(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("1.500", 1500.0), ("1,99", 1.99), ("1.500,50", 1500.5), ("250", 250.0)],
)
def test_numero_no_formato_brasileiro(entrada, esperado):
    """Confundir separador de milhar com decimal é erro de valor clássico."""
    assert _para_numero(entrada) == esperado


# -------------------------------------------------------------- interpretação


async def test_pergunta_do_enunciado_da_prova():
    i = await planner.planejar("quais produtos estão com estoque abaixo de 10 unidades?")
    assert i.ferramenta == "consultar_estoque_baixo"
    assert i.argumentos == {"limite": 10}
    assert i.confianca >= 0.9


async def test_estoque_baixo_sem_numero_usa_limite_padrao_com_menos_confianca():
    i = await planner.planejar("o que está acabando no estoque?")
    assert i.ferramenta == "consultar_estoque_baixo"
    assert i.argumentos == {"limite": 10}
    assert i.confianca < 0.9  # assumiu um valor, então admite menos certeza


async def test_faixa_de_preco():
    i = await planner.planejar("quais produtos custam entre 100 e 500 reais?")
    assert i.ferramenta == "buscar_produtos"
    assert i.argumentos == {"preco_min": 100.0, "preco_max": 500.0}


async def test_desambiguacao_entre_quantidade_e_dinheiro():
    """'menos de 100' é estoque ou preço? A unidade citada decide."""
    estoque = await planner.planejar("produtos com menos de 100 unidades em estoque")
    preco = await planner.planejar("produtos que custam menos de 100 reais")

    assert estoque.ferramenta == "consultar_estoque_baixo"
    assert preco.ferramenta == "buscar_produtos"
    assert preco.argumentos == {"preco_max": 100.0}


async def test_resumo_do_estoque():
    i = await planner.planejar("quanto vale meu estoque?")
    assert i.ferramenta == "resumo_do_estoque"


async def test_pergunta_fora_do_dominio_nao_e_interpretada():
    i = await planner.planejar("qual a previsão do tempo para amanhã?")
    assert i.ferramenta is None
    assert i.confianca == 0.0


# ----------------------------------------------------------------- guardrails


async def test_intencao_destrutiva_sem_alvo_fica_abaixo_do_limiar():
    """'apaga tudo' não pode virar um id chutado."""
    i = await planner.planejar("apaga tudo")
    assert i.ferramenta == "remover_produto"
    assert i.argumentos == {}
    assert i.confianca < 0.6


async def test_acao_destrutiva_exige_confirmacao():
    executor = Executor(session=None)  # não chega a executar, então não precisa de sessão
    interpretacao = Interpretacao(
        ferramenta="remover_produto",
        argumentos={"produto_id": 7},
        confianca=0.85,
        estrategia="teste",
        justificativa="teste",
    )

    resultado = await executor.executar(interpretacao, confirmado=False)

    assert resultado.status == "confirmacao_necessaria"
    assert resultado.dados["acao_pendente"] == "remover_produto"


async def test_confianca_baixa_impede_execucao():
    executor = Executor(session=None)
    interpretacao = Interpretacao(
        ferramenta="resumo_do_estoque",
        argumentos={},
        confianca=0.2,
        estrategia="teste",
        justificativa="teste",
    )

    assert (await executor.executar(interpretacao, confirmado=True)).status == "nao_compreendido"


async def test_ferramenta_inexistente_e_barrada():
    """Simula um LLM alucinando um nome de função que não existe."""
    executor = Executor(session=None)
    interpretacao = Interpretacao(
        ferramenta="dropar_banco_de_dados",
        argumentos={},
        confianca=0.99,
        estrategia="llm_ficticio",
        justificativa="teste",
    )

    assert (await executor.executar(interpretacao, confirmado=True)).status == "nao_compreendido"


async def test_argumento_fora_do_schema_e_barrado():
    """Simula um LLM inventando um parâmetro que a ferramenta não aceita."""
    executor = Executor(session=None)
    interpretacao = Interpretacao(
        ferramenta="consultar_estoque_baixo",
        argumentos={"limite": 10, "tabela": "usuarios; DROP TABLE produtos"},
        confianca=0.99,
        estrategia="llm_ficticio",
        justificativa="teste",
    )

    resultado = await executor.executar(interpretacao, confirmado=True)
    assert resultado.status == "erro_na_ferramenta"


async def test_tipo_errado_de_argumento_e_barrado():
    executor = Executor(session=None)
    interpretacao = Interpretacao(
        ferramenta="consultar_estoque_baixo",
        argumentos={"limite": "dez"},
        confianca=0.99,
        estrategia="teste",
        justificativa="teste",
    )

    assert (await executor.executar(interpretacao, confirmado=True)).status == "erro_na_ferramenta"


# ------------------------------------------------------------------ contratos


def test_todas_as_ferramentas_saem_nos_dois_formatos():
    """A promessa da Questão 9: as mesmas capacidades servem LLM e MCP."""
    assert len(esquema_function_calling()) == len(REGISTRO)
    assert len(esquema_mcp()) == len(REGISTRO)


def test_ferramenta_destrutiva_e_anunciada_como_tal_no_mcp():
    remover = next(f for f in esquema_mcp() if f["name"] == "remover_produto")
    assert remover["annotations"]["destructiveHint"] is True
    assert remover["annotations"]["requiresConfirmation"] is True


def test_ferramentas_de_leitura_nao_sao_marcadas_como_destrutivas():
    leitura = [f for f in esquema_mcp() if f["name"] != "remover_produto"]
    assert all(f["annotations"]["readOnlyHint"] for f in leitura)
