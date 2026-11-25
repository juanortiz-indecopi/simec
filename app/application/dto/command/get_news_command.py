from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetNewsCommand:
    # Normalizados; al menos uno está presente.
    name: str | None = None
    topic: str | None = None
    # True: consultar la web aunque la búsqueda ya esté guardada.
    refresh: bool = False
