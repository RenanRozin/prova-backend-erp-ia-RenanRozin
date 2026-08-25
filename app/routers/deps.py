"""Dependências compartilhadas pelos routers."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.redis_client import get_redis
from app.core.security import TokenError, decode_access_token

# auto_error=False para devolver 401 com corpo próprio em vez do 403 que o
# HTTPBearer entrega por padrão quando falta o header — 403 ali é semanticamente
# errado: o cliente não foi barrado por permissão, ele nem se identificou.
_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def usuario_autenticado(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Valida o JWT e devolve o `sub`. Protege todas as rotas de escrita."""
    if credenciais is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais ausentes",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credenciais.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return str(payload["sub"])


UsuarioDep = Annotated[str, Depends(usuario_autenticado)]
