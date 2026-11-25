"""Consultas recibidas y fotos (snapshots) de cada fuente: el registro de "qué se consultó, a qué
fuente y en qué fecha" que exige la trazabilidad del sistema."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


class QueryType(str, Enum):
    COMPANY_BY_RUC = "COMPANY_BY_RUC"
    PERSON_BY_DNI = "PERSON_BY_DNI"
    SUNARP_PARTIDA = "SUNARP_PARTIDA"
    INSTAGRAM_PROFILE = "INSTAGRAM_PROFILE"
    FACEBOOK_PAGE = "FACEBOOK_PAGE"
    NEWS_SEARCH = "NEWS_SEARCH"


class FetchMode(str, Enum):
    CACHE = "CACHE"      # Responde desde la BD si hay foto válida; si no, consulta la web.
    REFRESH = "REFRESH"  # El usuario pidió actualizar (?refresh=true): consulta la web siempre.


class ServedFrom(str, Enum):
    DATABASE = "DATABASE"  # Todas las fuentes salieron de la BD.
    LIVE = "LIVE"          # Todas las fuentes se consultaron en la web.
    MIXED = "MIXED"        # Parte de la BD y parte de la web (p.ej. un refresco que falló a medias).


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    """Última foto válida de una fuente para un parámetro, ya convertida a modelo de dominio."""

    snapshot_id: int
    source_name: str
    data: Any
    executed_at: datetime
    # Desde cuándo se considera posiblemente desactualizada. Solo informa: nunca re-consulta sola.
    stale_after: datetime | None = None

    def data_as(self, kind: type[T]) -> T | None:
        return self.data if isinstance(self.data, kind) else None

    def is_stale(self, now: datetime) -> bool:
        return self.stale_after is not None and now >= self.stale_after


@dataclass(frozen=True, slots=True)
class SourceOrigin:
    """De dónde salieron los datos de una fuente en esta respuesta."""

    source_name: str
    from_cache: bool  # True: se sirvió una foto guardada en la BD.
    data_fetched_at: datetime | None  # Cuándo se obtuvieron de la fuente; None si no hay datos.
    is_stale: bool = False  # La foto superó su vigencia: el frontend puede sugerir actualizar.


def served_from(origins: tuple[SourceOrigin, ...]) -> ServedFrom:
    cached = sum(1 for origin in origins if origin.from_cache)
    if cached == 0:
        return ServedFrom.LIVE
    return ServedFrom.DATABASE if cached == len(origins) else ServedFrom.MIXED
