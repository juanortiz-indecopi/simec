import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Final

# Únicas áreas registrales del buscador de partidas de SPRL, con el texto exacto del portal.
AREAS_REGISTRALES: Final[tuple[str, ...]] = (
    "Propiedad Inmueble Predial",
    "Propiedad Inmueble No Predial",
    "Personas Juridicas",
    "Personas Naturales",
    "Propiedad Vehicular",
    "Propiedad Mineria",
    "Registro de Naves y Embarcaciones (antes Registro de Embarcaciones Pesqueras)",
    "Propiedad Aeronaves",
    "Registro Mobiliario de Contratos",
    "Registro de Naves y Embarcaciones (antes Registro de Naves)",
)


def _clave_area(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip()


_AREAS_POR_CLAVE: Final = {_clave_area(a): a for a in AREAS_REGISTRALES}


def normalizar_area(texto: str) -> str | None:
    """Devuelve el área canónica ignorando mayúsculas, tildes y signos; None si no existe.

    Solo coincidencia exacta: "Propiedad Inmueble" o "Registro de Naves y Embarcaciones" son
    ambiguos y no se aceptan.
    """
    return _AREAS_POR_CLAVE.get(_clave_area(texto or ""))


class SunarpDocumentStatus(str, Enum):
    """Resultado de la descarga del asiento de inscripción en Síguelo Plus para un título."""
    DOWNLOADED = "DOWNLOADED"                      # Se descargó al menos un PDF
    NOT_FOUND = "NOT_FOUND"                        # Síguelo Plus no encontró el título
    OFFICE_NOT_AVAILABLE = "OFFICE_NOT_AVAILABLE"  # La oficina no existe en Síguelo Plus: consulta manual
    YEAR_NOT_AVAILABLE = "YEAR_NOT_AVAILABLE"      # El año no está en el desplegable de Síguelo Plus
    NO_INSCRIPTION_SEAT = "NO_INSCRIPTION_SEAT"    # El título no ofrece "Acceder al asiento de inscripción"
    ERROR = "ERROR"                                # Falla técnica (red, Cloudflare, tiempo agotado...)


@dataclass(frozen=True, slots=True)
class SunarpSeatDocument:
    """PDF del asiento de inscripción descargado desde Síguelo Plus."""
    partida: str
    file_path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class SunarpSeat:
    """Representa un título/asiento extraído del panel lateral."""
    year: str
    number: str
    original_text: str
    documents: tuple[SunarpSeatDocument, ...] = ()
    document_status: SunarpDocumentStatus | None = None
    document_detail: str | None = None


@dataclass(frozen=True, slots=True)
class SunarpRecord:
    """Consolidado final de la búsqueda en SUNARP."""
    partida: str
    seats: tuple[SunarpSeat, ...] = ()
