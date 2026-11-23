"""Catálogo inicial de fuentes.

`code` coincide con el SOURCE_NAME de cada extractor (AuditResult.source_name), que es como el
servicio relaciona una ejecución con su fuente.

Vigencia (cache_ttl_hours): solo marca los datos como posiblemente desactualizados; nunca
dispara una re-consulta automática.
  - Identidad (apis.net.pe DNI): cambia muy poco -> 180 días.
  - SUNAT: estado y condición del contribuyente cambian seguido -> 7 días.
  - SEACE / RNP: vigencias, accionistas y adjudicaciones -> 30 días.
  - SUNARP: asientos registrales históricos -> 90 días.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22 19:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = [
    {
        "code": "APIS_NET_PE_DNI",
        "name": "apis.net.pe - Consulta DNI (RENIEC)",
        "category": "IDENTITY",
        "base_url": "https://api.apis.net.pe",
        "cache_ttl_hours": 4320,
    },
    {
        "code": "APIS_NET_PE_RUC",
        "name": "apis.net.pe - Consulta RUC",
        "category": "TAX_REGISTRY",
        "base_url": "https://api.apis.net.pe",
        "cache_ttl_hours": 168,
    },
    {
        "code": "SUNAT_SCRAPER_RUC",
        "name": "SUNAT - Consulta RUC por número de RUC",
        "category": "TAX_REGISTRY",
        "base_url": "https://e-consultaruc.sunat.gob.pe",
        "cache_ttl_hours": 168,
    },
    {
        "code": "SUNAT_SCRAPER_DNI",
        "name": "SUNAT - Consulta RUC por DNI",
        "category": "TAX_REGISTRY",
        "base_url": "https://e-consultaruc.sunat.gob.pe",
        "cache_ttl_hours": 168,
    },
    {
        "code": "SEACE_PENTAHO_CDA_RUC",
        "name": "SEACE - Ficha de proveedor por RUC",
        "category": "PUBLIC_PROCUREMENT",
        "base_url": "https://bi.seace.gob.pe",
        "cache_ttl_hours": 720,
    },
    {
        "code": "SEACE_PENTAHO_CDA_DNI",
        "name": "SEACE - Proveedores vinculados a un DNI",
        "category": "PUBLIC_PROCUREMENT",
        "base_url": "https://bi.seace.gob.pe",
        "cache_ttl_hours": 720,
    },
    {
        "code": "RNP_SCRAPER_RUC",
        "name": "RNP - Inscripciones del proveedor por RUC",
        "category": "PUBLIC_PROCUREMENT",
        "base_url": "https://www.rnp.gob.pe",
        "cache_ttl_hours": 720,
    },
    {
        "code": "SUNARP_SPRL",
        "name": "SUNARP - SPRL: asientos de la partida registral",
        "category": "PROPERTY_REGISTRY",
        "base_url": "https://sprl.sunarp.gob.pe",
        "cache_ttl_hours": 2160,
    },
    {
        "code": "SUNARP_SIGUELO",
        "name": "SUNARP - Síguelo Plus: PDF del asiento de inscripción",
        "category": "PROPERTY_REGISTRY",
        "base_url": "https://sigueloplus.sunarp.gob.pe",
        "cache_ttl_hours": 2160,
    },
]


def upgrade() -> None:
    sources = sa.table(
        "sources",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("base_url", sa.Text),
        sa.column("cache_ttl_hours", sa.Integer),
        schema="simec",
    )
    op.bulk_insert(sources, SOURCES)


def downgrade() -> None:
    codes = ", ".join(f"'{source['code']}'" for source in SOURCES)
    op.execute(f"DELETE FROM simec.sources WHERE code IN ({codes})")
