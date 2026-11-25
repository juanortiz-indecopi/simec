"""Lectura determinista de una página de Facebook. No usa red ni navegador.

Los datos salen del JSON incrustado (los campos llevan su tipo, p.ej. INTRO_CARD_PROFILE_PHONE), y
la identidad se contrasta con los metadatos. El formulario de login siempre está presente y no
significa que la página esté bloqueada.
"""
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

from app.domain.models.facebook import (
    FacebookField,
    FacebookLink,
    FacebookMediaType,
    FacebookPost,
    normalize_page,
)
from app.infrastructure.outbound.extractors.shared.embedded_json import iter_dicts, nodes
from app.infrastructure.outbound.extractors.shared.links import clean_url, platform_of, text

_UNAVAILABLE: Final = re.compile(
    r"(?:contenido|página) no está disponible|(?:content|page) isn.t available", re.I
)
_BLOCKED: Final = re.compile(
    r"bloquead[oa] temporalmente|temporarily blocked|no eres un robot|not a robot|captcha", re.I
)
_NUMBER: Final = r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+)"
_FOLLOWERS: Final = re.compile(_NUMBER + r"\s+(?:seguidores|followers)", re.I)
_TALKING: Final = re.compile(_NUMBER + r"\s+personas? están? hablando", re.I)
_FOLLOWING: Final = re.compile(r"(\d+)\s+(?:seguidos|following)", re.I)
_MONTHS: Final = (
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
)
_DATE: Final = re.compile(r"(\d{1,2}) de (\w+) de (\d{4})")
# "Abierto ahora" depende de la hora de la consulta: no es un horario.
_MOMENTARY: Final = re.compile(r"(?:abierto|cerrado) ahora|(?:open|closed) now", re.I)
_OWNER_SUFFIX: Final = re.compile(r"\s+es responsable de esta página\.?$", re.I)
_EMAIL: Final = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class PageState(str, Enum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    NOT_A_PAGE = "NOT_A_PAGE"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PageReading:
    state: PageState
    details: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)  # Campos de FacebookPage.
    photo_url: str | None = None
    pending: bool = False  # Aún no cargan los detalles o la publicación.


def _text(value: Any) -> str | None:
    return text(value.get("text")) if isinstance(value, dict) else text(value)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _number(pattern: re.Pattern[str], source: str) -> int | None:
    match = pattern.search(source)
    return int(re.sub(r"\D", "", match.group(1))) if match else None


def _unwrap(url: Any) -> str | None:
    """Destino de una redirección l.facebook.com."""
    value = text(url)
    if value is None:
        return None
    parts = urlsplit(value)
    if parts.hostname in ("l.facebook.com", "lm.facebook.com"):
        return (parse_qs(parts.query).get("u") or [None])[0]
    return value


def _check_access(page: dict[str, Any], has_header: bool) -> PageReading | None:
    path = urlsplit(page["url"]).path
    if page["status"] in (401, 403, 429):
        return PageReading(PageState.BLOCKED, f"Facebook rechazó la consulta (HTTP {page['status']})")
    if path.startswith(("/login", "/checkpoint")):
        return PageReading(PageState.BLOCKED, "Facebook exige iniciar sesión o verificar el acceso")
    if has_header:
        return None
    if _UNAVAILABLE.search(page["body"]):
        return PageReading(
            PageState.NOT_FOUND, "Página no disponible: no existe, fue eliminada o está restringida"
        )
    if _BLOCKED.search(page["body"]):
        return PageReading(PageState.BLOCKED, "Facebook muestra un bloqueo o verificación")
    return PageReading(PageState.ERROR, "La página no trae los datos esperados")


def _header(scripts: list[str]) -> dict[str, Any] | None:
    for node in nodes(scripts, '"profile_header_renderer"'):
        renderer = node.get("profile_header_renderer")
        user = renderer.get("user") if isinstance(renderer, dict) else None
        if isinstance(user, dict) and text(user.get("name")) and user.get("id"):
            return user
    return None


def _raw_fields(scripts: list[str]) -> list[tuple[str, str, str | None]]:
    """(tipo, texto, url) de los detalles de la portada y de las pestañas de información."""
    found: list[tuple[str, str, str | None]] = []
    for node in nodes(scripts, '"timeline_context_list_item_type"'):
        kind, renderer = node.get("timeline_context_list_item_type"), node.get("renderer")
        item = renderer.get("context_item") if isinstance(renderer, dict) else None
        if isinstance(kind, str) and isinstance(item, dict) and (value := _text(item.get("title"))):
            found.append((kind.removeprefix("INTRO_CARD_").lower(), value, _unwrap(item.get("url"))))
    for node in nodes(scripts, '"field_type"'):
        kind = node.get("field_type")
        if isinstance(kind, str) and (value := _text(node.get("title"))):
            found.append((kind.lower(), value, _unwrap(node.get("link_url"))))
    return list(dict.fromkeys(found))


def _link_key(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}?{parts.query}"


def parse_fields(scripts: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    phones: dict[str, str] = {}
    emails: dict[str, str] = {}
    links: dict[str, FacebookLink] = {}
    other: dict[tuple[str, str], FacebookField] = {}

    for kind, value, url in _raw_fields(scripts):
        if kind in ("influencer_category", "category"):
            result.setdefault("category", value.rpartition("·")[2].strip() or value)
        elif kind == "address":
            result.setdefault("address", value)
        elif kind == "confirmed_owner_label":
            result.setdefault("responsible", value)
        elif kind == "business_hours":
            if not _MOMENTARY.match(value):
                result.setdefault("business_hours", value)
        elif kind == "confirmed_owner":
            result.setdefault("responsible", _OWNER_SUFFIX.sub("", value))
        elif "rating" in kind or "recommend" in kind:
            result.setdefault("rating", value)
        elif kind == "page_id":
            result.setdefault("page_id", value)
        elif kind == "creation_date":
            result.setdefault("created_on", parse_spanish_date(value))
        elif kind == "ad_status":
            result.setdefault("has_active_ads", parse_ad_status(value))
        elif kind in ("admin_info", "transparency_see_all"):
            continue
        elif "phone" in kind or "whatsapp" in kind:
            phones.setdefault(re.sub(r"\D", "", value)[-9:] or value, value)
        elif "email" in kind and _EMAIL.fullmatch(value):
            emails.setdefault(value.lower(), value)
        else:
            candidate = url or (value if kind == "website" else None)
            cleaned = clean_url(candidate) if candidate else None
            if cleaned is not None:
                links.setdefault(_link_key(cleaned[0]), FacebookLink(cleaned[0], platform_of(cleaned[1])))
            else:
                other.setdefault((kind, value), FacebookField(kind, value))
    return result | {
        "phones": tuple(phones.values()),
        "emails": tuple(emails.values()),
        "links": tuple(links.values()),
        "other_info": tuple(other.values()),
    }


def parse_spanish_date(value: str) -> date | None:
    match = _DATE.search(value.lower())
    if match is None or match.group(2) not in _MONTHS:
        return None
    try:
        return date(int(match.group(3)), _MONTHS.index(match.group(2)) + 1, int(match.group(1)))
    except ValueError:
        return None


def parse_ad_status(value: str) -> bool | None:
    lowered = value.lower()
    if "anuncios en circulación" not in lowered:
        return None
    return re.search(r"\bno\b", lowered) is None


def _post(node: dict[str, Any], account_id: str) -> FacebookPost | None:
    actors, created = node.get("actors"), _int(node.get("creation_time"))
    url = text(node.get("permalink_url"))
    if (
        node.get("__typename") != "Story"
        or not node.get("post_id")
        or created is None
        or url is None
        or urlsplit(url).hostname != "www.facebook.com"
        or not isinstance(actors, list)
        or not actors
        or not isinstance(actors[0], dict)
        or str(actors[0].get("id")) != account_id
        or not isinstance(node.get("comet_sections"), dict)
    ):
        return None
    content = node["comet_sections"].get("content")
    story = content.get("story") if isinstance(content, dict) else None
    message = story.get("message") if isinstance(story, dict) else None

    counts: dict[str, int | None] = {"reactions": None, "comments": None, "shares": None}
    for item in iter_dicts(node["comet_sections"].get("feedback")):
        reaction, share = item.get("reaction_count"), item.get("share_count")
        if isinstance(reaction, dict) and isinstance(share, dict):
            rendering = item.get("comment_rendering_instance")
            comments = rendering.get("comments") if isinstance(rendering, dict) else None
            counts = {
                "reactions": _int(reaction.get("count")),
                "comments": _int(comments.get("total_count")) if isinstance(comments, dict) else None,
                "shares": _int(share.get("count")),
            }
            break

    attachments = node.get("attachments")
    media_type = FacebookMediaType.NONE
    if isinstance(attachments, list) and attachments:
        media = attachments[0].get("media") if isinstance(attachments[0], dict) else None
        kind = media.get("__typename") if isinstance(media, dict) else None
        media_type = {"Photo": FacebookMediaType.PHOTO, "Video": FacebookMediaType.VIDEO}.get(
            kind, FacebookMediaType.OTHER
        )
    return FacebookPost(
        post_id=str(node["post_id"]),
        url=url,
        published_at=datetime.fromtimestamp(created, timezone.utc),
        media_type=media_type,
        text=_text(message),
        **counts,
    )


def _latest_post(candidates: Iterable[dict[str, Any]], account_id: str) -> FacebookPost | None:
    posts = [post for node in candidates if (post := _post(node, account_id)) is not None]
    return max(posts, key=lambda post: post.published_at, default=None)


def _same_key(requested: str, header: dict[str, Any], page_id: str | None) -> bool:
    if requested in (str(header["id"]), page_id):
        return True
    current = normalize_page(text(header.get("url")) or "")
    # Facebook ignora los puntos del username.
    return current is not None and current.replace(".", "") == requested.replace(".", "")


def read_main(page: dict[str, Any], key: str) -> PageReading:
    header = _header(page["json"])
    problem = _check_access(page, header is not None)
    if problem is not None or header is None:
        return problem or PageReading(PageState.ERROR)

    account_id, name = str(header["id"]), text(header["name"]) or ""
    delegate = header.get("delegate_page")
    page_id = str(delegate["id"]) if isinstance(delegate, dict) and delegate.get("id") else None
    if page_id is None:
        return PageReading(PageState.NOT_A_PAGE, "Es un perfil personal, no una página: no se leen sus datos")
    if not _same_key(key, header, page_id):
        return PageReading(PageState.ERROR, f"Facebook mostró otra página: {text(header.get('url'))}")
    metas = page["metas"]
    title = text(metas.get("og:title")) or ""
    if not title.startswith(name) or metas.get("al:android:url") != f"fb://profile/{account_id}":
        return PageReading(PageState.ERROR, "Los metadatos no confirman la identidad de la página")

    # El nombre lo escribe el administrador: se quita antes de leer los contadores.
    summary = (metas.get("og:description") or "").replace("\xa0", " ").removeprefix(name)
    social = header.get("profile_social_context")
    content = social.get("content") if isinstance(social, dict) else None
    social_text = " ".join(
        _text(item.get("text")) or "" for item in content or [] if isinstance(item, dict)
    ).replace("\xa0", " ")

    description = None
    for node in nodes(page["json"], '"best_description"'):
        if str(node.get("id")) == page_id and (description := _text(node.get("best_description"))):
            break
    photo = next(
        (
            url
            for candidate in (header.get("profilePicLarge"), header.get("profilePicMedium"))
            if isinstance(candidate, dict) and (url := text(candidate.get("uri")))
        ),
        None,
    )
    verified = header.get("show_verified_badge_on_profile")
    details = parse_fields(page["json"])
    post = _latest_post(nodes(page["json"], '"creation_time"'), account_id)
    fields = details | {
        "account_id": account_id,
        "page_id": page_id,
        "page_url": text(header.get("url")) or f"https://www.facebook.com/{account_id}",
        "name": name,
        "city": text(title.removeprefix(name).strip().removeprefix("|")),
        "description": description,
        "is_verified": verified if isinstance(verified, bool) else None,
        "followers": _number(_FOLLOWERS, summary),
        "following": _number(_FOLLOWING, social_text),
        "talking_about": _number(_TALKING, summary),
        "latest_post": post,
    }
    return PageReading(
        PageState.OK,
        fields=fields,
        photo_url=photo,
        pending=post is None or "category" not in details,
    )


def read_section(page: dict[str, Any], account_id: str) -> PageReading:
    """Pestañas "about" y "about_profile_transparency" de la misma página."""
    header = _header(page["json"])
    problem = _check_access(page, header is not None)
    if problem is not None or header is None:
        return problem or PageReading(PageState.ERROR)
    if str(header["id"]) != account_id:
        return PageReading(PageState.ERROR, "La pestaña corresponde a otra página")
    if not any(True for _ in nodes(page["json"], '"field_type"')):
        return PageReading(PageState.ERROR, "La pestaña no trae datos", pending=True)
    return PageReading(PageState.OK, fields=parse_fields(page["json"]))


def merge(main: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Completa la portada con una pestaña, sin duplicar ni reemplazar lo ya leído."""
    merged = dict(main)
    for name, value in extra.items():
        if name == "phones":
            seen = {re.sub(r"\D", "", p)[-9:] for p in merged[name]}
            merged[name] += tuple(p for p in value if re.sub(r"\D", "", p)[-9:] not in seen)
        elif name == "emails":
            seen = {e.lower() for e in merged[name]}
            merged[name] += tuple(e for e in value if e.lower() not in seen)
        elif name == "links":
            seen = {_link_key(link.url) for link in merged[name]}
            merged[name] += tuple(link for link in value if _link_key(link.url) not in seen)
        elif name == "other_info":
            merged[name] += tuple(item for item in value if item not in merged[name])
        elif merged.get(name) is None:
            merged[name] = value
    return merged
