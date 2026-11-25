import os
from pathlib import Path

from app.core.files import FILES_DIR


def photos_dir() -> Path:
    # Bajo FILES_DIR, como los PDF de SUNARP: FastAPI lo publica en /files.
    return Path(os.getenv("INSTAGRAM_FILES_DIR", os.path.join(FILES_DIR, "instagram")))
