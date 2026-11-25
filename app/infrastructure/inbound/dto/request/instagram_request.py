from typing import Annotated

from fastapi import Path
from pydantic import AfterValidator

from app.domain.models.instagram import USERNAME_PATTERN, normalize_username


def _validate_username(value: str) -> str:
    username = normalize_username(value)
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username no válido: hasta 30 letras, números, puntos o guiones bajos, sin puntos "
            "al inicio, al final ni seguidos"
        )
    return username


UsernamePathParam = Annotated[
    str,
    Path(
        max_length=60,
        description="Nombre de usuario de Instagram, con o sin `@`. No distingue mayúsculas.",
        examples=["nasa"],
    ),
    AfterValidator(_validate_username),
]
