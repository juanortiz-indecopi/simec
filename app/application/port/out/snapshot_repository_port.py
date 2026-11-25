"""Puerto de salida de persistencia: lo que los servicios necesitan para guardar y reutilizar las
consultas a las fuentes, sin saber qué base de datos hay detrás.

Flujo esperado de un servicio (p.ej. consulta por RUC):

    1. find_current(...)        Lectura corta: ¿qué fuentes tienen foto válida guardada?
    2. try_begin_refresh(...)   Reserva corta de las fuentes que hay que consultar en la web,
                                para que dos peticiones simultáneas no hagan el mismo scraping.
    3. (scraping)               SIN conexión a la BD: puede tardar minutos.
    4. save_outcome(...)        Una sola transacción corta: consulta, fotos, vínculos, punteros
                                de caché y liberación de las reservas.
       ó end_refresh(...)       Si el scraping se aborta antes de poder guardar.

Reglas que toda implementación debe cumplir:
  - Las fotos nunca se sobrescriben: cada ejecución es una foto nueva (historial).
  - Una ejecución ERROR o NO_DATA se registra, pero nunca reemplaza a la última foto válida.
  - Si la persistencia falla, se lanza PersistenceError; el servicio responde igual en vivo.
"""
from abc import ABC, abstractmethod
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.domain.models.audit import AuditResult
from app.domain.models.news import NewsArticle
from app.domain.models.party import PartyLink, PartyRef
from app.domain.models.query import FetchMode, QueryType, ServedFrom, StoredSnapshot


class PersistenceError(Exception):
    """La persistencia no está disponible o falló. El servicio debe seguir sin ella."""


@dataclass(frozen=True, slots=True)
class SourceExecution:
    """Resultado de ejecutar un extractor en esta consulta."""

    audit: AuditResult
    data: Any | None = None  # Modelo de dominio (CompanyProfile, SunatProfile, SunarpRecord...).
    raw: Any | None = None   # Respuesta original de la fuente, tal como la entregó el extractor.


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """Todo lo que se guarda al terminar una consulta, en una única transacción."""

    query_type: QueryType
    query_parameter: str
    # Clave normalizada con la que se buscará la foto la próxima vez: RUC, DNI u
    # "OFICINA|Area canonica|partida". Es la misma para todas las fuentes de la consulta.
    cache_key: str
    fetch_mode: FetchMode
    served_from: ServedFrom
    requested_at: datetime
    completed_at: datetime
    # Persona o empresa consultada; None si ninguna fuente permitió identificarla.
    subject: PartyRef | None = None
    # Fuentes consultadas en la web en esta petición (incluye las que fallaron).
    executions: tuple[SourceExecution, ...] = ()
    # Fotos servidas desde la BD en esta petición (trazabilidad: qué datos vio el usuario).
    reused_snapshot_ids: tuple[int, ...] = ()
    # Vínculos encontrados en las ejecuciones exitosas. Los vínculos previos de esa misma fuente
    # y sujeto que ya no aparezcan se marcan como inactivos.
    links: tuple[PartyLink, ...] = ()
    # Noticias obtenidas en vivo en esta consulta. Se guardan una sola vez y sin vincular a nadie.
    articles: tuple[NewsArticle, ...] = ()


class SnapshotRepositoryPort(ABC):
    @abstractmethod
    async def find_current(
        self, source_names: Collection[str], cache_key: str
    ) -> dict[str, StoredSnapshot]:
        """Última foto válida por fuente. Las fuentes sin foto no aparecen en el resultado."""

    @abstractmethod
    async def try_begin_refresh(
        self, source_names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        """Reserva las fuentes para consultarlas en la web y devuelve las que se lograron reservar.

        Una fuente ya reservada por otra petición no se devuelve, salvo que su reserva tenga más
        de `lease` (el proceso que la tomó murió o se colgó): entonces se toma de nuevo.
        """

    @abstractmethod
    async def refreshing(
        self, source_names: Collection[str], cache_key: str, lease: timedelta
    ) -> frozenset[str]:
        """Fuentes que otra petición está consultando ahora (reserva tomada hace menos de `lease`)."""

    @abstractmethod
    async def end_refresh(self, source_names: Collection[str], cache_key: str) -> None:
        """Libera reservas sin guardar nada (scraping cancelado o fallido antes de guardar)."""

    @abstractmethod
    async def save_outcome(self, outcome: QueryOutcome) -> None:
        """Guarda la consulta completa y libera las reservas de las fuentes ejecutadas."""
