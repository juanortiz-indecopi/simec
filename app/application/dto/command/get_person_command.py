import re
from dataclasses import dataclass
from typing import Final

DNI_PATTERN: Final = re.compile(r"[0-9]{8}")


@dataclass(frozen=True, slots=True)
class GetPersonCommand:
    dni: str
    # True: consultar todas las fuentes en la web aunque haya datos guardados.
    refresh: bool = False

    def __post_init__(self) -> None:
        if not DNI_PATTERN.fullmatch(self.dni):
            raise ValueError("DNI must have exactly 8 digits")
