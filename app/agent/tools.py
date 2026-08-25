"""Registro de ferramentas do ERP expostas ao agente.

## Esta é a peça central da Parte 5

Cada ferramenta é declarada com **JSON Schema** — exatamente o formato que um
provedor de LLM espera em tool/function calling e que um servidor MCP publica em
tools/list. A consequência prática: trocar o interpretador de regras por um LLM
de verdade não exige reescrever ferramenta nenhuma. Muda-se o planner; o
contrato, a validação e os guardrails continuam iguais.

É por isso que o registro não sabe o que é um LLM. Ele descreve **capacidades do
domínio**. Quem traduz linguagem natural em chamada é outra camada — e é
justamente a camada substituível.

## Metadados de segurança

Os campos destrutiva e exige_confirmacao não são decoração: o executor os lê
antes de qualquer execução. A regra de que o agente não apaga nada sem
confirmação humana mora no dado, junto da ferramenta, em vez de espalhada em ifs.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

Executor = Callable[[AsyncSession, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any]  # JSON Schema do objeto de argumentos
    executor: Executor
    destrutiva: bool = False
    exige_confirmacao: bool = False
    exemplos: list[str] = field(default_factory=list)


REGISTRO: dict[str, Ferramenta] = {}


def registrar(ferramenta: Ferramenta) -> Ferramenta:
    REGISTRO[ferramenta.nome] = ferramenta
    return ferramenta


# ---------------------------------------------------------------- implementações


async def _consultar_estoque_baixo(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    limite = int(args.get("limite", 10))
    stmt = (
        select(Product)
        .where(Product.quantidade_em_estoque <= limite)
        .order_by(Product.quantidade_em_estoque.asc(), Product.nome)
    )
    produtos = list((await session.execute(stmt)).scalars().all())
    return {
        "limite": limite,
        "total": len(produtos),
        "produtos": [
            {
                "id": p.id,
                "nome": p.nome,
                "quantidade_em_estoque": p.quantidade_em_estoque,
                "preco": str(p.preco),
            }
            for p in produtos
        ],
    }


async def _buscar_produtos(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(Product)
    nome = args.get("nome")
    if nome:
        stmt = stmt.where(Product.nome.ilike(f"%{nome}%"))

    preco_min = args.get("preco_min")
    if preco_min is not None:
        stmt = stmt.where(Product.preco >= Decimal(str(preco_min)))

    preco_max = args.get("preco_max")
    if preco_max is not None:
        stmt = stmt.where(Product.preco <= Decimal(str(preco_max)))

    limite = min(int(args.get("limite", 20)), 100)
    stmt = stmt.order_by(Product.nome).limit(limite)

    produtos = list((await session.execute(stmt)).scalars().all())
    return {
        "total": len(produtos),
        "filtros_aplicados": {k: v for k, v in args.items() if v is not None},
        "produtos": [
            {
                "id": p.id,
                "nome": p.nome,
                "preco": str(p.preco),
                "quantidade_em_estoque": p.quantidade_em_estoque,
            }
            for p in produtos
        ],
    }


async def _resumo_do_estoque(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    stmt = select(
        func.count(Product.id),
        func.coalesce(func.sum(Product.quantidade_em_estoque), 0),
        func.coalesce(func.sum(Product.preco * Product.quantidade_em_estoque), 0),
    )
    total_itens, total_unidades, valor = (await session.execute(stmt)).one()
    return {
        "total_produtos": total_itens,
        "total_unidades": int(total_unidades),
        "valor_total_estoque": str(Decimal(valor).quantize(Decimal("0.01"))),
    }


async def _detalhar_produto(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    produto = await session.get(Product, int(args["produto_id"]))
    if produto is None:
        return {"encontrado": False, "produto_id": args["produto_id"]}
    return {
        "encontrado": True,
        "produto": {
            "id": produto.id,
            "nome": produto.nome,
            "preco": str(produto.preco),
            "quantidade_em_estoque": produto.quantidade_em_estoque,
            "data_atualizacao": produto.data_atualizacao.isoformat(),
        },
    }


async def _remover_produto(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    produto = await session.get(Product, int(args["produto_id"]))
    if produto is None:
        return {"removido": False, "motivo": "produto inexistente"}
    nome = produto.nome
    await session.delete(produto)
    await session.commit()
    return {"removido": True, "produto_id": args["produto_id"], "nome": nome}


# -------------------------------------------------------------------- registro

registrar(
    Ferramenta(
        nome="consultar_estoque_baixo",
        descricao=(
            "Lista os produtos cujo estoque esta igual ou abaixo de um limite. "
            "Use quando o usuario perguntar sobre estoque baixo, falta de produto, "
            "ruptura ou necessidade de reposicao."
        ),
        parametros={
            "type": "object",
            "properties": {
                "limite": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 10,
                    "description": "Quantidade maxima em estoque para entrar na lista",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        executor=_consultar_estoque_baixo,
        exemplos=[
            "quais produtos estao com estoque abaixo de 10 unidades?",
            "o que esta acabando no estoque?",
        ],
    )
)

registrar(
    Ferramenta(
        nome="buscar_produtos",
        descricao=(
            "Busca produtos por parte do nome e/ou faixa de preco. Use para "
            "perguntas sobre quais produtos custam entre dois valores ou que "
            "contenham determinada palavra no nome."
        ),
        parametros={
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Trecho do nome do produto"},
                "preco_min": {"type": "number", "minimum": 0},
                "preco_max": {"type": "number", "minimum": 0},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "required": [],
            "additionalProperties": False,
        },
        executor=_buscar_produtos,
        exemplos=[
            "quais produtos custam entre 100 e 500 reais?",
            "me mostra os produtos com motor no nome",
        ],
    )
)

registrar(
    Ferramenta(
        nome="resumo_do_estoque",
        descricao=(
            "Devolve numeros consolidados do estoque: quantidade de produtos "
            "cadastrados, total de unidades e valor financeiro total."
        ),
        parametros={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        executor=_resumo_do_estoque,
        exemplos=["quanto vale meu estoque?", "quantos produtos eu tenho cadastrados?"],
    )
)

registrar(
    Ferramenta(
        nome="detalhar_produto",
        descricao="Mostra os dados completos de um produto especifico pelo seu id.",
        parametros={
            "type": "object",
            "properties": {"produto_id": {"type": "integer", "minimum": 1}},
            "required": ["produto_id"],
            "additionalProperties": False,
        },
        executor=_detalhar_produto,
        exemplos=["me mostra o produto 3", "detalhes do produto 7"],
    )
)

registrar(
    Ferramenta(
        nome="remover_produto",
        descricao=(
            "Remove um produto do cadastro. ACAO DESTRUTIVA e irreversivel: "
            "exige confirmacao explicita do usuario antes de executar."
        ),
        parametros={
            "type": "object",
            "properties": {"produto_id": {"type": "integer", "minimum": 1}},
            "required": ["produto_id"],
            "additionalProperties": False,
        },
        executor=_remover_produto,
        destrutiva=True,
        exige_confirmacao=True,
        exemplos=["apague o produto 5", "exclua o produto 12 do cadastro"],
    )
)


# --------------------------------------------------- exportacao dos contratos


def esquema_function_calling() -> list[dict[str, Any]]:
    """Ferramentas no formato de function calling dos provedores de LLM.

    E este o payload que iria junto do prompt no dia em que um LLM real entrar
    no lugar do planner de regras. Nada alem do planner precisa mudar.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": f.nome,
                "description": f.descricao,
                "parameters": f.parametros,
            },
        }
        for f in REGISTRO.values()
    ]


def esquema_mcp() -> list[dict[str, Any]]:
    """As mesmas ferramentas no formato de resposta de tools/list do MCP.

    Os campos sao praticamente os mesmos, o que mostra que a decisao entre
    function calling direto e servidor MCP e de transporte e governanca, nao de
    modelagem. A discussao esta na Questao 9.
    """
    return [
        {
            "name": f.nome,
            "description": f.descricao,
            "inputSchema": f.parametros,
            "annotations": {
                "destructiveHint": f.destrutiva,
                "readOnlyHint": not f.destrutiva,
                "requiresConfirmation": f.exige_confirmacao,
            },
        }
        for f in REGISTRO.values()
    ]
