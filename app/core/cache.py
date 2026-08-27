"""Camada fina sobre o Redis para cache de leitura.

## Estratégia adotada: cache-aside + invalidação explícita + versionamento

**Cache-aside** (lê o cache, se não achar vai ao banco e grava): o cache nunca
fica no caminho da escrita, então uma queda do Redis degrada latência, não
corretude — a API continua respondendo direto do Postgres.

**Registro individual** (`produto:{id}`) é invalidado por exclusão direta: toda
escrita naquele produto apaga a chave. Simples e exato.

**Listagens** são o problema difícil: a chave depende de filtro, ordenação e
paginação, então uma escrita afeta um número imprevisível de chaves e não dá para
apagar uma a uma sem varrer o Redis (`KEYS` trava o servidor; `SCAN` é O(n) e
corre atrás do próprio rabo sob escrita concorrente).

A saída é **versionar o namespace**: toda chave de listagem carrega a versão
corrente (`produtos:v7:<impressão-do-filtro>`) e qualquer escrita faz `INCR` na
versão. As chaves da v7 viram inalcançáveis no ato — invalidação O(1) — e somem
sozinhas pelo TTL. O custo é ficar com lixo em memória até o TTL expirar, o que é
barato e previsível.

**TTL curto (60s por padrão) em tudo**, como rede de segurança: se alguma escrita
escapar da invalidação (script, outro serviço, migração), a inconsistência tem
prazo de validade conhecido em vez de ser permanente.
"""

import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

PRODUTO_KEY = "produto:{id}"
PRODUTOS_VERSAO_KEY = "produtos:versao"
PRODUTOS_LISTA_KEY = "produtos:v{versao}:{impressao}"


def impressao_do_filtro(payload: dict[str, Any]) -> str:
    """Impressão digital estável dos parâmetros de uma listagem.

    `sort_keys` garante que a mesma consulta gere sempre a mesma chave,
    independente da ordem em que os parâmetros chegaram na query string.
    """
    canonico = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(canonico.encode("utf-8")).hexdigest()[:16]


async def versao_produtos(redis: Redis) -> int:
    """Versão corrente do namespace de listagens. Ausente = 1 (cache frio).

    Redis fora do ar devolve a versão 1 e a requisição segue: a chave montada
    não vai existir, o resultado é um MISS e a listagem vem do Postgres.
    """
    try:
        valor = await redis.get(PRODUTOS_VERSAO_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("cache indisponível ao ler a versão do namespace")
        return 1
    return int(valor) if valor else 1


async def invalidar_produto(redis: Redis, produto_id: int | None = None) -> None:
    """Chamada por toda escrita: derruba o registro e vira a versão das listagens."""
    try:
        async with redis.pipeline(transaction=False) as pipe:
            if produto_id is not None:
                pipe.delete(PRODUTO_KEY.format(id=produto_id))
            pipe.incr(PRODUTOS_VERSAO_KEY)
            await pipe.execute()
    except Exception:  # noqa: BLE001
        # O dado já foi gravado no Postgres; falhar aqui não pode desfazer a
        # operação de negócio. O risco assumido é uma entrada antiga voltar a
        # ser servida quando o Redis retornar — limitado pelo TTL de 60s.
        logger.warning(
            "cache indisponível na invalidação",
            extra={"context": {"produto_id": produto_id}},
        )


async def ler_json(redis: Redis, chave: str) -> Any | None:
    """Falha de cache nunca derruba a requisição — no pior caso é um MISS."""
    try:
        bruto = await redis.get(chave)
    except Exception:  # noqa: BLE001
        logger.warning("cache indisponível na leitura", extra={"context": {"chave": chave}})
        return None
    return json.loads(bruto) if bruto else None


async def gravar_json(redis: Redis, chave: str, valor: Any, ttl: int) -> None:
    try:
        await redis.set(chave, json.dumps(valor, default=str), ex=ttl)
    except Exception:  # noqa: BLE001
        logger.warning("cache indisponível na escrita", extra={"context": {"chave": chave}})
