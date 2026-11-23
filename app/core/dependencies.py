from functools import lru_cache

from app.application.port.usecase.get_company_use_case import GetCompanyUseCase
from app.application.port.usecase.get_person_use_case import GetPersonUseCase
from app.application.port.usecase.get_sunarp_use_case import GetSunarpUseCase
from app.application.services.get_company_service import GetCompanyService
from app.application.services.get_person_service import GetPersonService
from app.application.services.get_sunarp_service import GetSunarpService 
from app.infrastructure.outbound.extractors.profile.dni_adapter import ApisNetPeDniAdapter
from app.infrastructure.outbound.extractors.profile.ruc_adapter import ApisNetPeRucAdapter
from app.infrastructure.outbound.extractors.rnp.ruc_adapter import RnpRucAdapter
from app.infrastructure.outbound.extractors.seace.dni_adapter import SeaceDniAdapter
from app.infrastructure.outbound.extractors.seace.ruc_adapter import SeaceRucAdapter
from app.infrastructure.outbound.extractors.sunat.dni_adapter import SunatDniAdapter
from app.infrastructure.outbound.extractors.sunat.ruc_adapter import SunatRucAdapter
from app.infrastructure.outbound.extractors.sunarp.agent_extractor import SunarpAgentExtractor
from app.application.port.out.snapshot_repository_port import SnapshotRepositoryPort
from app.core.config import get_settings
from app.infrastructure.outbound.persistence.adapters.null_snapshot_repository import (
    NullSnapshotRepository,
)
from app.infrastructure.outbound.persistence.adapters.postgres_snapshot_repository import (
    PostgresSnapshotRepository,
)
from app.infrastructure.outbound.persistence.database import Database


@lru_cache
def get_database() -> Database | None:
    """Motor de PostgreSQL compartido por toda la app; None si DATABASE_URL no está configurada."""
    return Database.from_settings(get_settings())


@lru_cache
def get_snapshot_repository() -> SnapshotRepositoryPort:
    """Persistencia de consultas: PostgreSQL si está configurado; si no, una versión vacía."""
    database = get_database()
    if database is None:
        return NullSnapshotRepository()
    return PostgresSnapshotRepository(database, default_ttl_hours=get_settings().cache_default_ttl_hours)


@lru_cache
def get_company_use_case() -> GetCompanyUseCase:
    return GetCompanyService(
        profile=ApisNetPeRucAdapter(),
        seace=SeaceRucAdapter(),
        sunat=SunatRucAdapter(),
        rnp=RnpRucAdapter(),
        snapshots=get_snapshot_repository(),
    )


@lru_cache
def get_person_use_case() -> GetPersonUseCase:
    return GetPersonService(
        profile=ApisNetPeDniAdapter(),
        seace=SeaceDniAdapter(),
        sunat=SunatDniAdapter(),
        snapshots=get_snapshot_repository(),
    )


@lru_cache
def get_sunarp_use_case() -> GetSunarpUseCase:
    # El agente LLM+MCP tarda más que un extractor HTTP (con Gemini cada paso es más lento) y,
    # además, corre una vez más por cada título en Síguelo Plus para bajar su PDF: 30 minutos.
    return GetSunarpService(
        sunarp=SunarpAgentExtractor(),
        timeout_s=1800.0,
        snapshots=get_snapshot_repository(),
    )