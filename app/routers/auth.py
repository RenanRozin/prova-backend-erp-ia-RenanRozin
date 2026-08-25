"""Rotas de autenticação."""

from fastapi import APIRouter, HTTPException, status

from app.routers.deps import SessionDep
from app.schemas.auth import LoginRequest, Token
from app.services.auth import AuthService
from app.services.exceptions import CredenciaisInvalidas

router = APIRouter(prefix="/auth", tags=["autenticação"])


@router.post(
    "/login",
    response_model=Token,
    summary="Autentica e devolve um token JWT",
    responses={401: {"description": "Usuário ou senha inválidos"}},
)
async def login(dados: LoginRequest, session: SessionDep) -> Token:
    try:
        return await AuthService(session).autenticar(dados.username, dados.password)
    except CredenciaisInvalidas as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
