"""Autenticação: troca de credenciais por um JWT."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.repositories.user import UserRepository
from app.schemas.auth import Token
from app.services.exceptions import CredenciaisInvalidas


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = UserRepository(session)
        self.settings = get_settings()

    async def autenticar(self, username: str, password: str) -> Token:
        user = await self.repo.get_por_username(username)

        # Mesma resposta para usuário inexistente e senha errada: distinguir os
        # dois casos entrega ao atacante uma lista de usuários válidos.
        senha_confere = user is not None and verify_password(password, user.hashed_password)
        if user is None or not user.is_active or not senha_confere:
            raise CredenciaisInvalidas

        return Token(
            access_token=create_access_token(subject=user.username, extra_claims={"uid": user.id}),
            expires_in=self.settings.jwt_expire_minutes * 60,
        )
