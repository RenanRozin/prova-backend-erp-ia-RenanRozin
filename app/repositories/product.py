"""Acesso a dados de Produto.

O repositório existe para que o service não conheça SQLAlchemy. O ganho concreto
não é trocar de banco um dia — é poder testar a regra de negócio com um duplo em
memória e manter a consulta complexa num lugar só, em vez de espalhada por
endpoints.
"""

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.product import ProductFilter


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, produto_id: int) -> Product | None:
        return await self.session.get(Product, produto_id)

    async def get_por_nome(self, nome: str) -> Product | None:
        stmt = select(Product).where(func.lower(Product.nome) == nome.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def _aplica_filtros(self, stmt: Select, filtros: ProductFilter) -> Select:
        """Filtros montados como predicados compostos.

        Cada `if` adiciona um WHERE; nenhum valor é concatenado em string, tudo vai
        como parâmetro vinculado — é o que fecha a porta para SQL injection.
        """
        if filtros.nome:
            stmt = stmt.where(Product.nome.ilike(f"%{filtros.nome}%"))
        if filtros.preco_min is not None:
            stmt = stmt.where(Product.preco >= filtros.preco_min)
        if filtros.preco_max is not None:
            stmt = stmt.where(Product.preco <= filtros.preco_max)
        if filtros.estoque_baixo_ate is not None:
            stmt = stmt.where(Product.quantidade_em_estoque <= filtros.estoque_baixo_ate)
        return stmt

    async def listar(
        self, filtros: ProductFilter, limit: int, offset: int
    ) -> tuple[list[Product], int]:
        """Devolve a página e o total. Duas consultas de propósito: o COUNT sem
        ORDER BY nem LIMIT é bem mais barato que uma window function carregada
        junto de cada linha."""
        base = self._aplica_filtros(select(Product), filtros)

        coluna = getattr(Product, filtros.ordenar_por)
        direcao = asc if filtros.ordem == "asc" else desc
        # Desempate por id: sem uma coluna única no ORDER BY, duas páginas podem
        # repetir ou pular registros quando há valores iguais.
        pagina = base.order_by(direcao(coluna), Product.id).limit(limit).offset(offset)

        total_stmt = self._aplica_filtros(select(func.count(Product.id)), filtros)

        itens = list((await self.session.execute(pagina)).scalars().all())
        total = (await self.session.execute(total_stmt)).scalar_one()
        return itens, total

    async def listar_estoque_baixo(self, limite: int) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.quantidade_em_estoque <= limite)
            .order_by(Product.quantidade_em_estoque.asc(), Product.id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def criar(self, produto: Product) -> Product:
        self.session.add(produto)
        await self.session.flush()   # atribui o id sem encerrar a transação
        await self.session.refresh(produto)
        return produto

    async def remover(self, produto: Product) -> None:
        await self.session.delete(produto)
        await self.session.flush()
