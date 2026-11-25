"""Datos complementarios del perfil, tomados de la misma página. Todos son opcionales: si uno falta
o no se entiende queda en None, sin invalidar el perfil.
"""
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, Final

from app.domain.models.instagram import InstagramLink, InstagramMediaType, InstagramPost
from app.infrastructure.outbound.extractors.shared.links import clean_url, platform_of, text

_MENTION: Final = re.compile(r"(?<![\w.@/])@([A-Za-z0-9._]{1,30})(?![\w@])")
_POST_CODE: Final = re.compile(r"[\w-]{5,40}", re.ASCII)
_POSTS_COUNT: Final = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+)\s+(?:publicaciones|publicación|posts?)\b", re.I
)
_MONTHS: Final = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_POST_DATE: Final = re.compile(rf"\bon ((?:{_MONTHS}) \d{{1,2}}, \d{{4}})\b")
_MONTH_NUMBER: Final = {name: i for i, name in enumerate(_MONTHS.split("|"), 1)}
_MEDIA_TYPES: Final = {
    1: InstagramMediaType.PHOTO,
    2: InstagramMediaType.VIDEO,
    8: InstagramMediaType.CAROUSEL,
}


def count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def parse_links(value: Any) -> tuple[InstagramLink, ...] | None:
    if not isinstance(value, list):
        return None
    links: dict[str, InstagramLink] = {}
    for item in value:
        cleaned = clean_url(item.get("url")) if isinstance(item, dict) else None
        if cleaned is not None:
            url, host = cleaned
            links.setdefault(url, InstagramLink(url, platform_of(host), text(item.get("title"))))
    return tuple(links.values())


def parse_mentions(biography: Any, username: str) -> tuple[str, ...]:
    found = (m.rstrip(".").lower() for m in _MENTION.findall(biography or ""))
    return tuple(dict.fromkeys(m for m in found if m and m != username))


def parse_posts_count(node: dict[str, Any], og_description: str) -> int | None:
    exact = count(node.get("all_media_count"))
    if exact is not None:
        return exact
    # Los contadores van antes del " - "; después viene el nombre, que escribe el usuario.
    match = _POSTS_COUNT.search(og_description.partition(" - ")[0])
    return int(re.sub(r"\D", "", match.group(1))) if match else None


def _post_date(alt: Any, full_name: str | None) -> date | None:
    if not isinstance(alt, str):
        return None
    if full_name:  # El nombre lo escribe el usuario: no debe poder simular una fecha.
        alt = alt.replace(full_name, "", 1)
    match = _POST_DATE.search(alt)
    if match is None:
        return None
    month, day, year = match.group(1).replace(",", "").split()
    try:
        return datetime(int(year), _MONTH_NUMBER[month], int(day)).date()
    except ValueError:
        return None


def parse_posts(
    nodes: Iterable[dict[str, Any]], username: str, full_name: str | None
) -> tuple[InstagramPost, ...]:
    """Publicaciones propias visibles, de la más reciente a la más antigua (las sin fecha, al final)."""
    found: dict[str, tuple[int, InstagramPost]] = {}
    for node in nodes:
        code, user = node.get("code"), node.get("user")
        if (
            not isinstance(code, str)
            or not _POST_CODE.fullmatch(code)
            or "media_type" not in node
            or not isinstance(user, dict)
            or str(user.get("username", "")).lower() != username
            or code in found
        ):
            continue
        caption = node.get("caption")
        kind = "reel" if node.get("product_type") == "clips" else "p"
        pk = str(node.get("pk", ""))
        post = InstagramPost(
            url=f"https://www.instagram.com/{kind}/{code}/",
            media_type=_MEDIA_TYPES.get(node["media_type"], InstagramMediaType.OTHER)
            if isinstance(node["media_type"], int)
            else InstagramMediaType.OTHER,
            published_on=_post_date(node.get("accessibility_caption"), full_name),
            caption=text(caption.get("text")) if isinstance(caption, dict) else None,
        )
        found[code] = (int(pk) if pk.isascii() and pk.isdigit() else 0, post)
    # El ID desempata las del mismo día.
    ordered = sorted(
        found.values(), key=lambda item: (item[1].published_on or date.min, item[0]), reverse=True
    )
    return tuple(post for _, post in ordered)


def latest(posts: Iterable[InstagramPost]) -> InstagramPost | None:
    """La más reciente; None si alguna no tiene fecha, porque no se puede asegurar cuál es."""
    items = tuple(posts)
    if not items or any(post.published_on is None for post in items):
        return None
    return items[0]
