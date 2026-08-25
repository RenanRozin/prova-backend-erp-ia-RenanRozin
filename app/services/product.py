"""Regras de negócio de Produto: transação, cache e enfileiramento.

Esta é a única camada que conhece as três coisas ao mesmo tempo. O router não
sabe o que é Redis e o repositório não sabe o que é fila.
"""

import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.config import get_settings
from app.models.product import Product
from app.repositories.product import ProductRepository
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductFilter, ProductRead, ProductUpdate
from app.services.exceptions import ProdutoDuplicado, ProdutoNaoEncontrado
from app.workers.queue import enfileirar

logger = logging.getLogger(__name__)

# Abaixo disso o produto entra na régua de alerta. Numa evolução viraria uma
# coluna por produto (ponto de reposição), que é como um ERP de verdade trata.
LIMITE_ESTOQUE_BAIXO = 10


class ProductService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis
        self.repo = ProductRepository(session)
        self.settings = get_settings()

    # ------------------------------------------------------------------ leitura

    async def obter(self, produto_id: int) -> ProductRead:
        """Cache-aside no registro individual."""
        chave = cache.PRODUTO_KEY.format(id=produto_id)

        em_cache = await cache.ler_json(self.redis, chave)
        if em_cache is not None:
            logger.info("cache hit", extra={"context": {"chave": chave}})
            return ProductRead.model_validate(em_cache)

        produto = await self.repo.get(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado(produto_id)

        dto = ProductRead.model_validate(produto)
        await cache.gravar_json(
            self.redis, chave, dto.model_dump(mode="json"), self.settings.cache_ttl_seconds
        )
        return dto

    async def listar(self, filtros: ProductFilter, limit: int, offset: int) -> Page[ProductRead]:
        """Cache-aside na listagem, com a versão do namespace embutida na chave.

        A justificativa completa da estratégia está no módulo app.core.cache.
        """
        versao = await cache.versao_produtos(self.redis)
        impressao = cache.impressao_do_filtro(
            {**filtros.model_dump(mode="json"), "limit": limit, "offset": offset}
        )
        chave = cache.PRODUTOS_LISTA_KEY.format(versao=versao, impressao=impressao)

        em_cache = await cache.ler_json(self.redis, chave)
        if em_cache is not None:
            logger.info("cache hit", extra={"context": {"chave": chave}})
            return Page[ProductRead].model_validate(em_cache)

        itens, total = await self.repo.listar(filtros, limit=limit, offset=offset)
        pagina = Page[ProductRead](
            items=[ProductRead.model_validate(p) for p in itens],
            total=total,
            limit=limit,
            offset=offset,
        )
        await cache.gravar_json(
            self.redis, chave, pagina.model_dump(mode="json"), self.settings.cache_ttl_seconds
        )
        return pagina

    # ------------------------------------------------------------------ escrita

    async def criar(self, dados: ProductCreate) -> ProductRead:
        if await self.repo.get_por_nome(dados.nome):
            raise ProdutoDuplicado(dados.nome)

        produto = await self.repo.criar(Product(**dados.model_dump()))
        await self.session.commit()

        # A invalidação vem DEPOIS do commit. Invalidar antes abre uma janela em
        # que outra requisição repovoa o cache com o dado velho — e a transação
        # ainda por cima pode ser desfeita.
        await cache.invalidar_produto(self.redis, produto.id)
        await self._checar_estoque_baixo(produto)
        return ProductRead.model_validate(produto)

    async def atualizar(self, produto_id: int, dados: ProductUpdate) -> ProductRead:
        produto = await self.repo.get(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado(produto_id)

        alteracoes = dados.model_dump(exclude_unset=True)
        novo_nome = alteracoes.get("nome")
        if novo_nome and novo_nome.lower() != produto.nome.lower():
            if await self.repo.get_por_nome(novo_nome):
                raise ProdutoDuplicado(novo_nome)

        for campo, valor in alteracoes.items():
            setattr(produto, campo, valor)

        await self.session.commit()
        await self.session.refresh(produto)

        await cache.invalidar_produto(self.redis, produto_id)
        await self._checar_estoque_baixo(produto)
        return ProductRead.model_validate(produto)

    async def remover(self, produto_id: int) -> None:
        produto = await self.repo.get(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado(produto_id)

        await self.repo.remover(produto)
        await self.session.commit()
        await cache.invalidar_produto(self.redis, produto_id)

    # --------------------------------------------------------------------- fila

    async def _checar_estoque_baixo(self, produto: Product) -> None:
        """Enfileira a verificação em vez de fazê-la dentro da requisição.

        Hoje a tarefa é barata, mas é justamente o gancho que na vida real vira
        e-mail, webhook e integração com compras: trabalho lento e sujeito a
        falha externa, que não pode segurar a resposta do usuário nem derrubar
        uma venda porque o servidor de e-mail caiu.
        """
        if produto.quantidade_em_estoque > LIMITE_ESTOQUE_BAIXO:
            return
        await enfileirar(
            "registrar_alerta_estoque_baixo",
            produto_id=produto.id,
            limite=LIMITE_ESTOQUE_BAIXO,
        )
