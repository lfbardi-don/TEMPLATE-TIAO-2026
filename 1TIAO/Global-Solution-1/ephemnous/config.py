"""Configuração via variáveis de ambiente (lê do .env quando presente)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DATABASE_URL no ambiente sobrescreve este default (igual ao docker-compose.yml).
    database_url: str = "postgresql://ephemnous:ephemnous@localhost:5432/ephemnous"


settings = Settings()
