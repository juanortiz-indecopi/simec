"""Configuración central de la aplicación, leída de variables de entorno y del archivo .env.

Por ahora solo agrupa lo relacionado con la base de datos y la caché de consultas. Las variables
de los extractores (SUNARP, LLM, archivos) siguen leyéndose en sus propios módulos.

Si DATABASE_URL no está definida, la persistencia queda deshabilitada y la API funciona como
puente de consulta en vivo, igual que antes de incorporar la base de datos.
"""
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Conexión de la aplicación (usuario simec_app: solo lee y escribe datos).
    database_url: SecretStr | None = None
    # Conexión de migraciones (usuario simec_owner: crea y modifica tablas). La usa Alembic.
    database_migration_url: SecretStr | None = None
    database_schema: str = Field(default="simec", pattern=r"^[a-z_][a-z0-9_]*$")

    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout_s: float = Field(default=30.0, gt=0)
    database_echo: bool = False

    # Horas tras las que un dato guardado se marca como posiblemente desactualizado (is_stale).
    # No dispara re-consultas automáticas: solo el usuario actualiza con ?refresh=true.
    cache_default_ttl_hours: int = Field(default=720, ge=1)

    @property
    def database_enabled(self) -> bool:
        return self.database_url is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
