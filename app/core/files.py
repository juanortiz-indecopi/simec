"""Configuración de los archivos generados por los extractores (p.ej. PDFs de SUNARP).

Los archivos se guardan bajo FILES_DIR y FastAPI los sirve en FILES_URL_PREFIX, de modo que
`files/sunarp/CUSCO_11156404/x.pdf` se publica como `<base>/files/sunarp/CUSCO_11156404/x.pdf`.

Variables de entorno:
  FILES_DIR        carpeta raíz de archivos (por defecto "files").
  PUBLIC_BASE_URL  URL pública del backend para armar enlaces absolutos detrás de un proxy
                   (p.ej. "https://simec.indecopi.gob.pe"). Si no se define, se usa la URL
                   con la que llegó la petición.
"""
import os
from pathlib import Path
from typing import Final
from urllib.parse import quote

FILES_DIR: Final = os.getenv("FILES_DIR", "files")
FILES_URL_PREFIX: Final = "/files"
PUBLIC_BASE_URL: Final = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def build_file_url(file_path: str, request_base_url: str) -> str | None:
    """URL pública de un archivo guardado bajo FILES_DIR; None si está fuera de esa carpeta."""
    try:
        relative = Path(file_path).resolve().relative_to(Path(FILES_DIR).resolve())
    except ValueError:
        return None
    base = PUBLIC_BASE_URL or request_base_url.rstrip("/")
    return f"{base}{FILES_URL_PREFIX}/{quote(relative.as_posix())}"
