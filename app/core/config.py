"""Configuração central da aplicação.

Uma única fonte de verdade para variáveis de ambiente, validada pelo Pydantic no
startup. A escolha é deliberada: se faltar uma variável obrigatória, o processo
morre ao subir — e não no meio de uma requisição, em produção, às três da manhã.
"""

from functools import lru_cache

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Aplicação ---
    app_name: str = "ERP Core API"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    # Echo do SQLAlchemy separado do DEBUG: ligado junto, o SQLAlchemy instala
    # handler proprio e cada linha de log sai duas vezes (a dele e a nossa em JSON).
    sql_echo: bool = False

    # --- PostgreSQL ---
    postgres_user: str = "erp"
    postgres_password: SecretStr = SecretStr("erp")
    postgres_db: str = "erp"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Segurança ---
    jwt_secret_key: SecretStr = SecretStr("dev-only-nao-usar-em-producao")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- Seed ---
    seed_admin_username: str = "admin"
    seed_admin_password: SecretStr = SecretStr("admin123")

    # --- Cache ---
    cache_ttl_seconds: int = 60

    @computed_field
    @property
    def database_url(self) -> str:
        """DSN assíncrono (asyncpg). Montado a partir das partes para que a senha
        nunca precise aparecer inteira num único env var copiado entre serviços."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """Cacheado: as configurações são lidas uma vez por processo. O `lru_cache`
    também dá um ponto único de override nos testes (`get_settings.cache_clear()`)."""
    return Settings()
