"""Mocks dos serviços vizinhos consultados pela visão agregada (Parte 2).

Representam três microsserviços do ERP desenhado na Parte 1 — estoque,
financeiro e cadastro de clientes. Cada um simula latência com asyncio.sleep e
aceita injeção de falha e de lentidão, para que o comportamento degradado possa
ser demonstrado e testado sem depender de sorte.
"""

import asyncio
import random
from typing import Any

from app.core.resiliencia import FalhaPermanente, FalhaTransitoria

# Latência típica de cada serviço, em segundos (mínimo, máximo). O financeiro é
# de propósito o mais lento: é o padrão real em ERP, porque costuma consolidar
# dados de mais de uma origem antes de responder.
LATENCIA = {
    "estoque": (0.04, 0.12),
    "financeiro": (0.10, 0.35),
    "cliente": (0.03, 0.10),
}


class SimulacaoDeFalha:
    """Controla o que vai dar errado nesta requisição.

    Existe para tornar o caminho de falha demonstrável: sem isso, provar
    degradação graciosa dependeria de esperar o azar acontecer.
    """

    def __init__(
        self,
        indisponiveis: set[str] | None = None,
        lentas: set[str] | None = None,
        invalidas: set[str] | None = None,
        falhas_transitorias: dict[str, int] | None = None,
    ) -> None:
        self.indisponiveis = indisponiveis or set()
        self.lentas = lentas or set()
        self.invalidas = invalidas or set()
        # fonte -> quantas vezes falhar antes de funcionar. É o cenário que o
        # retry existe para resolver: a falha passageira.
        self.falhas_transitorias = dict(falhas_transitorias or {})

    async def aplicar(self, fonte: str) -> None:
        if fonte in self.invalidas:
            raise FalhaPermanente(f"{fonte}: requisição rejeitada (400)")

        if fonte in self.indisponiveis:
            raise FalhaTransitoria(f"{fonte}: serviço indisponível (503)")

        if fonte in self.lentas:
            # Dorme muito além de qualquer timeout razoável, para que quem
            # chamou tenha de desistir.
            await asyncio.sleep(30)

        restantes = self.falhas_transitorias.get(fonte, 0)
        if restantes > 0:
            self.falhas_transitorias[fonte] = restantes - 1
            raise FalhaTransitoria(
                f"{fonte}: falha transitória (tentativas restantes: {restantes - 1})"
            )


async def _latencia(fonte: str) -> None:
    minimo, maximo = LATENCIA[fonte]
    await asyncio.sleep(random.uniform(minimo, maximo))


async def consultar_estoque(produto_id: int, simulacao: SimulacaoDeFalha) -> dict[str, Any]:
    await simulacao.aplicar("estoque")
    await _latencia("estoque")
    return {
        "produto_id": produto_id,
        "disponivel": 42,
        "reservado": 8,
        "em_transito": 15,
        "deposito": "CD-JOINVILLE",
    }


async def consultar_financeiro(cliente_id: int, simulacao: SimulacaoDeFalha) -> dict[str, Any]:
    await simulacao.aplicar("financeiro")
    await _latencia("financeiro")
    return {
        "cliente_id": cliente_id,
        "limite_credito": "50000.00",
        "credito_utilizado": "18450.75",
        "titulos_em_aberto": 3,
        "situacao": "adimplente",
    }


async def consultar_cliente(cliente_id: int, simulacao: SimulacaoDeFalha) -> dict[str, Any]:
    await simulacao.aplicar("cliente")
    await _latencia("cliente")
    return {
        "cliente_id": cliente_id,
        "razao_social": "Metalúrgica Norte Catarinense Ltda",
        "cnpj": "12.345.678/0001-90",
        "cidade": "Joinville",
        "uf": "SC",
        "classificacao": "A",
    }
