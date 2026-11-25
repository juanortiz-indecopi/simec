import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Final

MAX_TERM_LENGTH: Final = 120
# Sin comillas, dos puntos ni paréntesis: no se admiten operadores del buscador (site:, intitle:...).
_TERM: Final = re.compile(r"[\w&.,'’/+\- ]+")


def normalize_term(value: str | None) -> str | None:
    """Minúsculas y espacios simples. None si está vacío; ValueError si no es un texto válido."""
    text = " ".join((value or "").split()).lower()
    if not text:
        return None
    # "-palabra" y "+palabra" serían operadores; el guion interior (coca-cola) se conserva.
    text = " ".join(re.sub(r"(^|\s)[-+]+", r"\1", text).split())
    if not 2 <= len(text) <= MAX_TERM_LENGTH or not _TERM.fullmatch(text) or not re.search(r"\w", text):
        raise ValueError("Use de 2 a 120 caracteres: letras, números, espacios y & . , ' / + -")
    return text


def build_query(name: str | None, topic: str | None) -> str:
    """Consulta para el buscador y clave de caché: el nombre como frase exacta, el tema como palabras."""
    return " ".join(part for part in (f'"{name}"' if name else None, topic) if part)


def words(text: str) -> str:
    """Solo palabras, sin tildes ni signos, para comparar textos."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return " ".join(re.findall(r"\w+", "".join(c for c in decomposed if not unicodedata.combining(c))))


@dataclass(frozen=True, slots=True)
class NewsArticle:
    title: str
    url: str  # Enlace de Google News: redirige al medio.
    article_id: str
    outlet: str | None = None
    outlet_url: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NewsSearch:
    query: str
    articles: tuple[NewsArticle, ...] = ()
    reached_limit: bool = False  # La fuente devolvió su máximo: puede haber más noticias.
