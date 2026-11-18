from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class GetSunarpCommand:
    oficina: str
    area: str
    partida: str