import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.dependencies import get_database
from app.core.files import FILES_DIR, FILES_URL_PREFIX
from app.infrastructure.inbound.controller.v1.router import api_router
from app.infrastructure.inbound.docs.openapi import API_METADATA


def _configure_app_logging() -> None:
    """Muestra en consola los logs INFO de `app.*`; uvicorn solo configura sus propios loggers."""
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-9s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)
        app_logger.propagate = False


_configure_app_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    database = get_database()
    if database is None:
        logger.warning("DATABASE_URL no configurada: la API funciona sin persistencia (modo puente).")
    elif await database.ping():
        logger.info("Conectado a PostgreSQL (esquema %s).", database.schema)
    else:
        # No se detiene el arranque: las consultas en vivo siguen funcionando sin guardar resultados.
        logger.error("PostgreSQL no responde al iniciar: la API arranca sin persistencia efectiva.")
    try:
        yield
    finally:
        if database is not None:
            await database.dispose()


app = FastAPI(**API_METADATA, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

# Archivos generados por los extractores (p.ej. PDFs de asientos de SUNARP), accesibles desde el front.
os.makedirs(FILES_DIR, exist_ok=True)
app.mount(FILES_URL_PREFIX, StaticFiles(directory=FILES_DIR), name="files")
