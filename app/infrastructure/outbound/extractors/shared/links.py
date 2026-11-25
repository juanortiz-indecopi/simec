"""Limpieza y clasificación de enlaces declarados en perfiles. No visita los enlaces."""
import re
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PLATFORMS: Final = {
    "facebook.com": "FACEBOOK",
    "fb.com": "FACEBOOK",
    "fb.me": "FACEBOOK",
    "instagram.com": "INSTAGRAM",
    "threads.com": "THREADS",
    "threads.net": "THREADS",
    "linkedin.com": "LINKEDIN",
    "tiktok.com": "TIKTOK",
    "youtube.com": "YOUTUBE",
    "youtu.be": "YOUTUBE",
    "x.com": "X",
    "twitter.com": "X",
    "wa.me": "WHATSAPP",
    "whatsapp.com": "WHATSAPP",
    "t.me": "TELEGRAM",
    "telegram.me": "TELEGRAM",
    "linktr.ee": "LINK_AGGREGATOR",
    "beacons.ai": "LINK_AGGREGATOR",
    "bio.link": "LINK_AGGREGATOR",
    "linkin.bio": "LINK_AGGREGATOR",
}
_TRACKING: Final = frozenset({"fbclid", "gclid", "igsh", "igshid"})


def text(value: Any) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def platform_of(host: str) -> str:
    for domain, platform in _PLATFORMS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return "WEB"


def clean_url(value: Any) -> tuple[str, str] | None:
    """(URL sin parámetros de rastreo, host); None si no es un enlace web."""
    url = text(value)
    if url is None:
        return None
    if "://" not in url and not re.match(r"[a-z][a-z0-9+.-]*:(?!\d)", url, re.I):
        url = f"https://{url}"
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or "." not in host:
        return None
    query = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query if k.lower() not in _TRACKING and not k.lower().startswith("utm_")]
    if len(kept) != len(query):  # Solo se reescribe si hay algo que quitar.
        parts = parts._replace(query=urlencode(kept))
    return urlunsplit(parts), host
