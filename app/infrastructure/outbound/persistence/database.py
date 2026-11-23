"""Motor asíncrono de PostgreSQL y fábrica de sesiones.

Regla de uso: una sesión equivale a una transacción corta. Los repositorios abren
`database.session()` solo para leer o guardar, nunca mientras corre un extractor: el scraping
(que en SUNARP puede tardar más de 20 minutos) se hace antes, sin conexión tomada del pool.
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(
        self,
        url: str,
        *,
        schema: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout_s: float = 30.0,
        echo: bool = False,
    ) -> None:
        self.schema = schema
        self._engine: AsyncEngine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout_s,
            pool_pre_ping=True,   # Descarta conexiones muertas (reinicio de PostgreSQL, red).
            pool_recycle=1800,    # Renueva conexiones cada 30 min para evitar cortes por inactividad.
            echo=echo,
            connect_args={
                "server_settings": {
                    "application_name": "simec-backend",
                    "search_path": f"{schema},public",
                    "timezone": "UTC",
                }
            },
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database | None":
        """Crea el motor si DATABASE_URL está configurada; None si la persistencia está deshabilitada."""
        if settings.database_url is None:
            return None
        return cls(
            settings.database_url.get_secret_value(),
            schema=settings.database_schema,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout_s=settings.database_pool_timeout_s,
            echo=settings.database_echo,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Transacción corta: confirma al salir sin errores y revierte si algo falla."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """True si PostgreSQL responde; nunca lanza excepción."""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("PostgreSQL no responde: %s: %s", type(exc).__name__, exc)
            return False

    async def dispose(self) -> None:
        await self._engine.dispose()
