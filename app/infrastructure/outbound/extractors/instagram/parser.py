"""Lectura determinista de la página de un perfil. No usa red ni navegador.

La fuente principal es el JSON incrustado; los metadatos y el texto visible solo lo verifican. Ante
cualquier discrepancia el resultado es ERROR: nunca se devuelven datos dudosos.
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

from app.domain.models.instagram import InstagramMediaType
from app.infrastructure.outbound.extractors.instagram.details import (
    count,
    latest,
    parse_links,
    parse_mentions,
    parse_posts,
    parse_posts_count,
    text,
)
from app.infrastructure.outbound.extractors.shared.embedded_json import nodes

_NOT_AVAILABLE = re.compile(
    r"(?:página|perfil|profile) no está disponible|(?:page|profile) isn.t available", re.I
)
_PRIVATE = re.compile(
    r"cuenta (?:es )?privada|perfil (?:es )?privado|(?:account|profile) is private", re.I
)
_BLOCKED = re.compile(
    r"espera unos minutos|wait a few minutes|no eres un robot|not a robot|captcha"
    r"|actividad sospechosa|suspicious activity",
    re.I,
)
_OG_TITLE = re.compile(r"(?P<name>.*?)\s*\(@(?P<user>[\w.]+)\)", re.S)
_OG_TITLE_NO_NAME = re.compile(r"@(?P<user>[\w.]+)(?:\s|$)")
_DESCRIPTION_BIO = re.compile(r'(?:en|on) Instagram: "(.*)"\s*$', re.S)


class PageState(str, Enum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PageReading:
    state: PageState
    details: str | None = None
    user: dict[str, Any] | None = None  # Campos de InstagramProfile más photo_url.
    posts_pending: bool = False  # Perfil completo, pero sus publicaciones aún no cargan.


def _clean(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _embedded_user(scripts: list[str], username: str) -> dict[str, Any] | None:
    for node in nodes(scripts, '"biography"'):
        # Sin estos campos es un bloque de enrutamiento, no el perfil.
        if str(node.get("username", "")).lower() == username and {
            "biography",
            "full_name",
            "is_private",
        } <= node.keys():
            return node
    return None


def _meta_identity(metas: dict[str, str]) -> tuple[str | None, str]:
    title = metas.get("og:title") or ""
    match = _OG_TITLE.match(title)
    if match:
        return match["user"].lower(), _clean(match["name"])
    match = _OG_TITLE_NO_NAME.match(title)
    return (match["user"].lower(), "") if match else (None, "")


def _shows_private_notice(main: str, node: dict[str, Any]) -> bool:
    """Busca el aviso fuera del nombre y la biografía, que los escribe el usuario."""
    own = {_clean(x) for x in f"{node['full_name'] or ''}\n{node['biography'] or ''}".splitlines()}
    return any(_PRIVATE.search(x) for x in main.splitlines() if _clean(x) not in own)


def read_page(page: dict[str, Any], username: str) -> PageReading:
    path = urlsplit(page["url"]).path
    if page["status"] in (401, 403, 429):
        return PageReading(PageState.BLOCKED, f"Instagram rechazó la consulta (HTTP {page['status']})")
    if path.startswith(("/accounts/", "/challenge")):
        return PageReading(PageState.BLOCKED, "Instagram exige iniciar sesión o verificar el acceso")
    # Se mira el título: una biografía podría contener la misma frase.
    if _NOT_AVAILABLE.search(page["title"]):
        return PageReading(
            PageState.NOT_FOUND, "Perfil no disponible: no existe, fue eliminado o está restringido"
        )
    if path.strip("/").lower() != username:
        return PageReading(PageState.ERROR, f"Instagram redirigió a otra página: {path}")

    node = _embedded_user(page["json"], username)
    if node is None:
        if page["password"] or _BLOCKED.search(page["body"]):
            return PageReading(PageState.BLOCKED, "Instagram muestra un muro de acceso o verificación")
        return PageReading(PageState.ERROR, "La página no trae los datos del perfil")

    is_private = node["is_private"]
    if not isinstance(is_private, bool):
        return PageReading(PageState.ERROR, "La página no indica si el perfil es privado")
    meta_user, meta_name = _meta_identity(page["metas"])
    if meta_user != username:
        return PageReading(PageState.ERROR, "Los metadatos no confirman el username")
    if meta_name != _clean(node["full_name"]):
        return PageReading(PageState.ERROR, "El nombre no coincide con los metadatos")
    if not page["main"].strip():
        return PageReading(PageState.ERROR, "El contenido visible no terminó de cargar")
    if is_private != _shows_private_notice(page["main"], node):
        return PageReading(PageState.ERROR, "La privacidad no coincide con el aviso visible")
    bio = _DESCRIPTION_BIO.search(page["metas"].get("description") or "")
    if bio and _clean(bio.group(1)) != _clean(node["biography"]):
        return PageReading(PageState.ERROR, "La biografía no coincide con los metadatos")

    hd = node.get("hd_profile_pic_url_info")
    photo = (hd.get("url") if isinstance(hd, dict) else None) or node.get("profile_pic_url")
    posts_count = parse_posts_count(node, page["metas"].get("og:description") or "")
    posts = () if is_private else parse_posts(
        nodes(page["json"], '"media_type"'), username, text(node["full_name"])
    )
    verified = node.get("is_verified")
    return PageReading(
        PageState.OK,
        user={
            "username": username,
            "full_name": text(node["full_name"]),
            "biography": text(node["biography"]),
            "is_private": is_private,
            "photo_url": photo,
            "account_id": str(node["pk"]) if node.get("pk") else None,
            "is_verified": verified if isinstance(verified, bool) else None,
            "followers": count(node.get("follower_count")),
            "following": count(node.get("following_count")),
            "posts_count": posts_count,
            "links": parse_links(node.get("bio_links")),
            "mentions": parse_mentions(node["biography"], username),
            "threads_username": text(node.get("text_post_app_badge_label"))
            if node.get("show_text_post_app_badge") is True
            else None,
            "latest_post": latest(posts),
            "latest_photo": latest(p for p in posts if p.media_type is InstagramMediaType.PHOTO),
        },
        posts_pending=not is_private and not posts and posts_count != 0,
    )
