from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetFacebookPageCommand:
    page: str  # Clave normalizada (username o ID). Es también la clave de caché.
    ruc: str | None = None  # Si se indica, se compara la página con los datos de esta empresa.
    # True: consultar Facebook en la web aunque la página ya esté guardada.
    refresh: bool = False
