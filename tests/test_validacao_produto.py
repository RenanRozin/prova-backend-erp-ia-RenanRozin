"""Validação de entrada de Produto.

Testes puros: não sobem banco, não sobem app. Rodam em milissegundos e é por
isso que valem — teste de validação que precisa de Docker ninguém roda antes do
commit.
"""

import pytest
from pydantic import ValidationError

from app.schemas.product import ProductCreate, ProductFilter, ProductUpdate


def test_produto_valido():
    p = ProductCreate(nome="Rolamento 6203ZZ", preco="24.50", quantidade_em_estoque=8)
    assert p.nome == "Rolamento 6203ZZ"
    assert str(p.preco) == "24.50"


@pytest.mark.parametrize("preco", ["-0.01", "-1", "-1000"])
def test_preco_negativo_e_recusado(preco):
    with pytest.raises(ValidationError):
        ProductCreate(nome="Item valido", preco=preco)


def test_preco_zero_e_aceito():
    """Zero é diferente de negativo: brinde e amostra existem no catálogo real."""
    assert ProductCreate(nome="Amostra gratis", preco="0").preco == 0


@pytest.mark.parametrize("nome", ["12345", "1.999,00", "42", "  7  "])
def test_nome_numerico_e_recusado(nome):
    with pytest.raises(ValidationError):
        ProductCreate(nome=nome, preco="10.00")


@pytest.mark.parametrize("nome", ["", "   ", "a"])
def test_nome_vazio_ou_curto_e_recusado(nome):
    with pytest.raises(ValidationError):
        ProductCreate(nome=nome, preco="10.00")


def test_nome_com_numero_no_meio_e_valido():
    """A regra proíbe nome que É um número, não nome que CONTÉM número —
    senão metade de um catálogo industrial seria rejeitada."""
    assert ProductCreate(nome="Parafuso M8 x 40", preco="0.85").nome == "Parafuso M8 x 40"


def test_nome_e_normalizado_com_strip():
    assert ProductCreate(nome="  Chapa de aco  ", preco="1").nome == "Chapa de aco"


def test_estoque_negativo_e_recusado():
    with pytest.raises(ValidationError):
        ProductCreate(nome="Item valido", preco="1", quantidade_em_estoque=-1)


def test_update_exige_ao_menos_um_campo():
    with pytest.raises(ValidationError):
        ProductUpdate()


def test_update_aceita_campo_isolado():
    u = ProductUpdate(preco="99.90")
    assert u.model_dump(exclude_unset=True) == {"preco": u.preco}


def test_update_nao_valida_nome_ausente():
    """Regressão: a primeira versão do schema quebrava com AttributeError ao
    receber PATCH sem o campo nome."""
    assert ProductUpdate(quantidade_em_estoque=5).nome is None


def test_filtro_recusa_faixa_de_preco_invertida():
    with pytest.raises(ValidationError):
        ProductFilter(preco_min=500, preco_max=100)


def test_filtro_aceita_faixa_coerente():
    f = ProductFilter(preco_min=100, preco_max=500)
    assert f.preco_min < f.preco_max
