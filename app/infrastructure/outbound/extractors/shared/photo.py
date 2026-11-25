"""Descarga de fotos de perfil (Meta): se validan y se guardan con su hash, sin pisar las anteriores."""
import hashlib
import io
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from PIL import Image
from playwright.async_api import BrowserContext

ALLOWED_HOSTS: Final = (".cdninstagram.com", ".fbcdn.net")
EXTENSIONS: Final = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_BYTES: Final = 5 * 1024 * 1024
TIMEOUT_MS: Final = 15_000


def is_allowed_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").endswith(ALLOWED_HOSTS)


def save_photo(content: bytes, name: str, directory: Path) -> str:
    if not content or len(content) > MAX_BYTES:
        raise ValueError("tamaño de foto inválido")
    with Image.open(io.BytesIO(content), formats=list(EXTENSIONS)) as image:
        image.load()
        extension = EXTENSIONS[image.format or ""]
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:12]
    path = directory / f"{name}_{digest}.{extension}"
    path.write_bytes(content)
    return path.as_posix()


async def download_photo(
    context: BrowserContext, url: str | None, name: str, directory: Path
) -> str:
    if not url or not is_allowed_url(url):
        raise ValueError("URL de foto ausente o no permitida")
    response = await context.request.get(url, timeout=TIMEOUT_MS, max_redirects=0)
    if not response.ok:
        raise ValueError(f"HTTP {response.status}")
    return save_photo(await response.body(), name, directory)
