import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Final

USERNAME_PATTERN: Final = re.compile(r"(?!.*\.\.)(?!\.)[a-z0-9._]{1,30}(?<!\.)")
_PROFILE_URL: Final = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([^/?#]+)/?(?:[?#].*)?")


def normalize_username(value: str) -> str:
    """Acepta `usuario`, `@usuario` o la URL del perfil. No valida el formato."""
    text = value.strip().lower()
    match = _PROFILE_URL.fullmatch(text)
    return (match.group(1) if match else text).removeprefix("@")


class InstagramMediaType(str, Enum):
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    CAROUSEL = "CAROUSEL"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class InstagramLink:
    url: str
    platform: str  # FACEBOOK, LINKEDIN, WHATSAPP, LINK_AGGREGATOR, WEB...
    title: str | None = None


@dataclass(frozen=True, slots=True)
class InstagramPost:
    url: str
    media_type: InstagramMediaType
    published_on: date | None = None
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class InstagramProfile:
    username: str
    profile_url: str
    is_private: bool
    full_name: str | None = None
    biography: str | None = None
    photo_path: str | None = None  # Copia local: la URL de Instagram caduca.
    # Opcionales: None = no se obtuvo (o perfil guardado antes de existir el campo); () = no tiene.
    account_id: str | None = None  # No cambia aunque cambie el username.
    is_verified: bool | None = None
    followers: int | None = None
    following: int | None = None
    posts_count: int | None = None
    links: tuple[InstagramLink, ...] | None = None
    mentions: tuple[str, ...] | None = None
    threads_username: str | None = None
    latest_post: InstagramPost | None = None
    latest_photo: InstagramPost | None = None  # La foto más reciente entre las visibles.
