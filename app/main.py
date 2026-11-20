import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.files import FILES_DIR, FILES_URL_PREFIX
from app.infrastructure.inbound.controller.v1.router import api_router
from app.infrastructure.inbound.docs.openapi import API_METADATA

app = FastAPI(**API_METADATA)

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
