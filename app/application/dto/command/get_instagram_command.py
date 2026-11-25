from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetInstagramCommand:
    username: str  # Normalizado: minúsculas y sin @. Es también la clave de caché.
    # True: consultar Instagram en la web aunque el perfil ya esté guardado.
    refresh: bool = False
