from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetSunarpCommand:
    oficina: str
    area: str
    partida: str
    # True: consultar SUNARP en la web aunque la partida ya esté guardada.
    refresh: bool = False

    @property
    def cache_key(self) -> str:
        """Clave con la que se guarda la partida: la oficina sin importar mayúsculas."""
        return f"{self.oficina.strip().upper()}|{self.area}|{self.partida.strip()}"
