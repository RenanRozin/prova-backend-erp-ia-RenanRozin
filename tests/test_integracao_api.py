"""Testes de integração contra a stack do docker compose.

Pulam sozinhos quando a stack não está de pé, para que `pytest` continue
utilizável sem Docker. Testes que quebram a suíte por causa de infraestrutura
ausente treinam o time a ignorar a suíte inteira.

Como rodar:
    docker compose up -d
    pytest tests/test_integracao_api.py
"""

import os

import httpx
import pytest

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
USUARIO = os.getenv("SEED_ADMIN_USERNAME", "admin")
SENHA = os.getenv("SEED_ADMIN_PASSWORD", "admin123")


def _stack_no_ar() -> bool:
    # Margem folgada de proposito: com 2s, a verificacao falhava no boot frio do
    # pytest e a suite inteira de integracao pulava em silencio — o pior tipo de
    # teste, o que finge estar tudo bem.
    try:
        return httpx.get(f"{BASE}/health/live", timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _stack_no_ar(), reason="stack do docker compose nao esta no ar"
)


@pytest.fixture
async def cliente():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        yield c


@pytest.fixture
async def token(cliente):
    r = await cliente.post("/auth/login", json={"username": USUARIO, "password": SENHA})
    r.raise_for_status()
    return r.json()["access_token"]


async def test_readiness_confirma_postgres_e_redis(cliente):
    r = await cliente.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"postgres": "ok", "redis": "ok"}


async def test_escrita_sem_token_e_recusada(cliente):
    r = await cliente.post("/produtos", json={"nome": "Sem token", "preco": 1})
    assert r.status_code == 401


async def test_login_com_senha_errada(cliente):
    r = await cliente.post("/auth/login", json={"username": USUARIO, "password": "errada"})
    assert r.status_code == 401


async def test_ciclo_completo_de_vida_do_produto(cliente, token):
    cabecalho = {"Authorization": f"Bearer {token}"}
    nome = f"Produto de teste {os.urandom(4).hex()}"

    criado = await cliente.post(
        "/produtos",
        headers=cabecalho,
        json={"nome": nome, "preco": "123.45", "quantidade_em_estoque": 7},
    )
    assert criado.status_code == 201
    produto_id = criado.json()["id"]

    try:
        # Duas leituras: a segunda deve vir do cache, com o mesmo conteúdo.
        primeira = await cliente.get(f"/produtos/{produto_id}")
        segunda = await cliente.get(f"/produtos/{produto_id}")
        assert primeira.json() == segunda.json()

        duplicado = await cliente.post(
            "/produtos", headers=cabecalho, json={"nome": nome, "preco": "1"}
        )
        assert duplicado.status_code == 409

        alterado = await cliente.patch(
            f"/produtos/{produto_id}", headers=cabecalho, json={"preco": "999.99"}
        )
        assert alterado.status_code == 200
        assert alterado.json()["preco"] == "999.99"

        # A leitura seguinte não pode devolver o preço antigo do cache.
        depois = await cliente.get(f"/produtos/{produto_id}")
        assert depois.json()["preco"] == "999.99"
    finally:
        removido = await cliente.delete(f"/produtos/{produto_id}", headers=cabecalho)
        assert removido.status_code == 204

    assert (await cliente.get(f"/produtos/{produto_id}")).status_code == 404


async def test_agregado_degrada_sem_derrubar_a_resposta(cliente):
    r = await cliente.get("/agregado/visao-360", params={"indisponivel": "estoque"})
    corpo = r.json()

    assert r.status_code == 200
    assert corpo["completo"] is False
    assert corpo["fontes"]["estoque"]["status"] == "indisponivel"
    # As outras duas fontes precisam ter sobrevivido à falha da primeira.
    assert corpo["fontes"]["financeiro"]["status"] == "ok"
    assert corpo["fontes"]["cliente"]["status"] == "ok"


async def test_agente_responde_a_pergunta_do_enunciado(cliente):
    r = await cliente.post(
        "/agente/perguntar",
        json={"texto": "quais produtos estão com estoque abaixo de 10 unidades?"},
    )
    corpo = r.json()

    assert r.status_code == 200
    assert corpo["status"] == "respondido"
    assert corpo["interpretacao"]["ferramenta"] == "consultar_estoque_baixo"
    assert corpo["dados"]["limite"] == 10


async def test_agente_nao_apaga_sem_confirmacao(cliente, token):
    cabecalho = {"Authorization": f"Bearer {token}"}
    criado = await cliente.post(
        "/produtos",
        headers=cabecalho,
        json={"nome": f"Alvo do guardrail {os.urandom(4).hex()}", "preco": "1"},
    )
    produto_id = criado.json()["id"]

    try:
        sem_confirmar = await cliente.post(
            "/agente/perguntar", json={"texto": f"apague o produto {produto_id}"}
        )
        assert sem_confirmar.json()["status"] == "confirmacao_necessaria"

        # E o produto continua lá.
        assert (await cliente.get(f"/produtos/{produto_id}")).status_code == 200
    finally:
        await cliente.delete(f"/produtos/{produto_id}", headers=cabecalho)
