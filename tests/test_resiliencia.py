"""Política de timeout, retry e orçamento (Parte 2).

O que se testa aqui não é "a função roda", é o **contrato de falha**: quantas
vezes tenta, quando desiste e se respeita o tempo prometido. É a parte que
costuma passar despercebida até o dia do incidente.
"""

import asyncio
import time

from app.core.resiliencia import FalhaPermanente, FalhaTransitoria, com_resiliencia


async def test_sucesso_na_primeira_tentativa():
    async def operacao():
        return {"ok": True}

    r = await com_resiliencia("fonte", operacao, timeout=1, tentativas=3)

    assert r.sucesso
    assert r.tentativas == 1
    assert r.dados == {"ok": True}


async def test_retry_recupera_de_falha_transitoria():
    chamadas = {"n": 0}

    async def operacao():
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise FalhaTransitoria("indisponivel")
        return "recuperou"

    r = await com_resiliencia("fonte", operacao, timeout=1, tentativas=3, backoff_base=0.001)

    assert r.sucesso
    assert r.tentativas == 3
    assert chamadas["n"] == 3


async def test_falha_permanente_nao_e_repetida():
    """Repetir um 4xx é desperdício — e, em escrita, é como se cria duplicidade."""
    chamadas = {"n": 0}

    async def operacao():
        chamadas["n"] += 1
        raise FalhaPermanente("400: payload invalido")

    r = await com_resiliencia("fonte", operacao, timeout=1, tentativas=5, backoff_base=0.001)

    assert r.status == "invalido"
    assert chamadas["n"] == 1


async def test_timeout_marca_fonte_como_indisponivel():
    async def operacao():
        await asyncio.sleep(5)

    r = await com_resiliencia("lenta", operacao, timeout=0.05, tentativas=2, backoff_base=0.001)

    assert r.status == "indisponivel"
    assert "timeout" in (r.erro or "")


async def test_esgotadas_as_tentativas_devolve_resultado_e_nao_excecao():
    """O ponto central da degradação graciosa: a função NUNCA levanta, para que
    o gather do endpoint sempre complete e as outras fontes sobrevivam."""

    async def operacao():
        raise FalhaTransitoria("503")

    r = await com_resiliencia("fonte", operacao, timeout=1, tentativas=2, backoff_base=0.001)

    assert not r.sucesso
    assert r.tentativas == 2
    assert r.erro is not None


async def test_orcamento_total_limita_o_tempo_gasto():
    """Sem orçamento, 3 tentativas de 0,2s custariam 0,6s ao usuário."""

    async def operacao():
        await asyncio.sleep(5)

    inicio = time.perf_counter()
    r = await com_resiliencia(
        "lenta", operacao, timeout=0.2, tentativas=5, backoff_base=0.001, orcamento_total=0.3
    )
    decorrido = time.perf_counter() - inicio

    assert not r.sucesso
    # Margem generosa para não virar teste instável em máquina carregada.
    assert decorrido < 0.6, f"orcamento estourado: {decorrido:.3f}s"


async def test_chamadas_em_paralelo_sao_mais_rapidas_que_em_serie():
    async def operacao():
        await asyncio.sleep(0.1)
        return "ok"

    inicio = time.perf_counter()
    resultados = await asyncio.gather(
        *(com_resiliencia(f"fonte{i}", operacao, timeout=1) for i in range(3))
    )
    decorrido = time.perf_counter() - inicio

    assert all(r.sucesso for r in resultados)
    # Em série seriam 0,3s. Em paralelo, ~0,1s.
    assert decorrido < 0.25, f"as chamadas nao rodaram em paralelo: {decorrido:.3f}s"
