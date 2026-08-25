"""CRUD de Produtos (Parte 3).

O router só faz três coisas: validar entrada (via Pydantic), chamar o service e
traduzir erro de domínio em status HTTP. Regra de negócio aqui dentro é o começo
do caminho para um endpoint de 300 linhas que ninguém consegue testar.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.routers.deps import RedisDep, SessionDep, UsuarioDep
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductFilter, ProductRead, ProductUpdate
from app.services.exceptions import ProdutoDuplicado, ProdutoNaoEncontrado
from app.services.product import ProductService

router = APIRouter(prefix="/produtos", tags=["produtos"])


@router.get(
    "",
    response_model=Page[ProductRead],
    summary="Lista produtos com filtros e paginação",
)
async def listar_produtos(
    session: SessionDep,
    redis: RedisDep,
    filtros: Annotated[ProductFilter, Depends()],
    limit: Annotated[int, Query(ge=1, le=100, description="Itens por página")] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProductRead]:
    """Endpoint de leitura com cache Redis (ver estratégia em app.core.cache).

    O teto de 100 em `limit` é proposital: sem ele, um `limit=1000000` vira um
    jeito legítimo de derrubar a API.
    """
    return await ProductService(session, redis).listar(filtros, limit=limit, offset=offset)


@router.get("/{produto_id}", response_model=ProductRead, summary="Busca um produto por id")
async def obter_produto(produto_id: int, session: SessionDep, redis: RedisDep) -> ProductRead:
    try:
        return await ProductService(session, redis).obter(produto_id)
    except ProdutoNaoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um produto",
)
async def criar_produto(
    dados: ProductCreate,
    session: SessionDep,
    redis: RedisDep,
    usuario: UsuarioDep,
) -> ProductRead:
    try:
        return await ProductService(session, redis).criar(dados)
    except ProdutoDuplicado as exc:
        # 409 e não 400: a requisição está correta, o conflito é com o estado
        # atual do servidor.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/{produto_id}", response_model=ProductRead, summary="Atualiza campos de um produto")
async def atualizar_produto(
    produto_id: int,
    dados: ProductUpdate,
    session: SessionDep,
    redis: RedisDep,
    usuario: UsuarioDep,
) -> ProductRead:
    try:
        return await ProductService(session, redis).atualizar(produto_id, dados)
    except ProdutoNaoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ProdutoDuplicado as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.delete(
    "/{produto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um produto",
)
async def remover_produto(
    produto_id: int,
    session: SessionDep,
    redis: RedisDep,
    usuario: UsuarioDep,
) -> Response:
    try:
        await ProductService(session, redis).remover(produto_id)
    except ProdutoNaoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
