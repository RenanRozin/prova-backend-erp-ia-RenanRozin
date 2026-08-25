"""Hash de senha e emissão/validação de JWT.

Escolhas:
- **bcrypt direto** em vez de `passlib`: o passlib está sem release desde 2020 e
  quebra com bcrypt 4.x. A API do bcrypt é pequena o suficiente para não precisar
  de wrapper.
- **HS256** (segredo simétrico) porque aqui só um serviço emite e valida o token.
  Num cenário de microsserviços real — o da Parte 1 — a escolha seria RS256/EdDSA:
  o serviço de identidade assina com a chave privada e os demais só precisam da
  pública, sem compartilhar segredo entre times.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


class TokenError(Exception):
    """Token ausente, expirado, malformado ou com assinatura inválida."""


def hash_password(plain: str) -> str:
    # bcrypt trunca em 72 bytes silenciosamente; truncar explicitamente deixa o
    # comportamento visível em vez de virar surpresa com senha longa.
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        # Hash corrompido no banco não deve derrubar o login com 500.
        return False


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        "iss": settings.app_name,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # Lista explícita de algoritmos: sem isso o token poderia chegar com
            # `alg: none` e ser aceito. É a falha clássica de implementação de JWT.
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
