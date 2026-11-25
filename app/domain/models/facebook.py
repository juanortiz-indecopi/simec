import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Final
from urllib.parse import parse_qs, urlsplit

PAGE_KEY_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9.\-]{1,79}")
_HOST: Final = re.compile(r"(?:[a-z0-9-]+\.)?(?:facebook|fb)\.com")
_RUC: Final = re.compile(r"(?:10|15|16|17|20)\d{9}")
_TABS: Final = frozenset({"about", "photos", "videos", "reels", "reviews", "mentions", "followers"})
_RESERVED: Final = frozenset(
    "ads business directory dialog events gaming groups hashtag help home.php l.php legal login login.php "
    "marketplace media messages pages people permalink.php pg photo photo.php photos plugins policies "
    "posts privacy profile.php public r.php recover reel reels search settings share sharer sharer.php "
    "story.php stories tr video videos watch p".split()
)


def normalize_page(value: str) -> str | None:
    """Clave de la página: username en minúsculas o ID numérico. None si no identifica una página.

    Acepta username, ID o URL (con parámetros, `profile.php?id=`, `/people/Nombre/ID`, `/p/Nombre-ID`).
    """
    raw = value.strip()
    lowered = raw.lower().removeprefix("https://").removeprefix("http://")
    if "/" not in lowered and "?" not in lowered:
        key = lowered.removeprefix("@")
        if _HOST.fullmatch(key):
            return None
        # Un RUC suelto es un error del usuario, no un ID de Facebook.
        return None if _RUC.fullmatch(key) else _valid(key)
    try:
        url = urlsplit("https://" + lowered)
        host = url.hostname or ""
    except ValueError:
        return None
    if not _HOST.fullmatch(host):
        return None
    parts = [p for p in url.path.split("/") if p]
    if not parts:
        return None
    if parts == ["profile.php"]:
        ids = parse_qs(url.query).get("id", [""])
        return ids[0] if re.fullmatch(r"[0-9]{5,20}", ids[0]) else None
    if parts[0] in ("people", "pages") and len(parts) == 3 and re.fullmatch(r"[0-9]{5,20}", parts[2]):
        return parts[2]
    if parts[0] == "p" and len(parts) == 2:
        match = re.search(r"-([0-9]{5,20})$", parts[1])
        return match.group(1) if match else None
    if parts[0] == "pg":
        parts = parts[1:]
    if not parts or len(parts) > 2 or (len(parts) == 2 and parts[1] not in _TABS):
        return None
    return _valid(parts[0])


def _valid(key: str) -> str | None:
    return key if PAGE_KEY_PATTERN.fullmatch(key) and key not in _RESERVED else None


class FacebookMediaType(str, Enum):
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    OTHER = "OTHER"  # Varias fotos, enlace, evento...
    NONE = "NONE"  # Solo texto.


@dataclass(frozen=True, slots=True)
class FacebookLink:
    url: str
    platform: str


@dataclass(frozen=True, slots=True)
class FacebookField:
    """Dato publicado que aún no tiene campo propio."""

    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class FacebookPost:
    post_id: str
    url: str
    published_at: datetime
    media_type: FacebookMediaType
    text: str | None = None
    reactions: int | None = None
    comments: int | None = None  # Solo la cantidad: el contenido es de terceros.
    shares: int | None = None


@dataclass(frozen=True, slots=True)
class FacebookPage:
    key: str
    page_url: str
    account_id: str  # No cambia aunque cambie el username.
    name: str
    page_id: str | None = None
    category: str | None = None
    description: str | None = None
    city: str | None = None
    address: str | None = None
    responsible: str | None = None  # "es responsable de esta página"
    is_verified: bool | None = None
    followers: int | None = None
    following: int | None = None
    talking_about: int | None = None
    rating: str | None = None
    business_hours: str | None = None
    phones: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()
    links: tuple[FacebookLink, ...] = ()
    other_info: tuple[FacebookField, ...] = ()
    created_on: date | None = None  # Pestaña "Transparencia de la página".
    has_active_ads: bool | None = None
    photo_path: str | None = None
    latest_post: FacebookPost | None = None
    # Pestañas opcionales que no se pudieron leer (p.ej. "about").
    missing_sections: tuple[str, ...] = ()


class MatchResult(str, Enum):
    PROBABLE = "PROBABLE"
    POSSIBLE = "POSSIBLE"
    NO_EVIDENCE = "NO_EVIDENCE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True, slots=True)
class CompanyFacts:
    ruc: str
    names: tuple[str, ...]  # Razón social y nombre comercial.
    addresses: tuple[str, ...] = ()
    places: tuple[str, ...] = ()  # Distrito, provincia y departamento.
    activities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PageVerification:
    """Comparación de la página con los registros de la empresa. Nunca confirma: lo hace un analista."""

    ruc: str
    result: MatchResult
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
