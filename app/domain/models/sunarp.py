from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class SunarpSeat:
    """Representa un título/asiento extraído del panel lateral."""
    year: str
    number: str
    original_text: str

@dataclass(frozen=True, slots=True)
class SunarpRecord:
    """Consolidado final de la búsqueda en SUNARP."""
    partida: str
    seats: tuple[SunarpSeat, ...] = ()