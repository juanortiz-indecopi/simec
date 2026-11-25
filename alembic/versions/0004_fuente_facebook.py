"""Agrega las páginas de Facebook al catálogo de fuentes.

Si la API ya registró la fuente sola (queda como UNCLASSIFIED), se completan sus datos.
Vigencia de 30 días: solo marca `is_stale`; nunca re-consulta.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO simec.sources (code, name, category, base_url, cache_ttl_hours)
        VALUES ('FACEBOOK_PAGE', 'Facebook - Página de empresa',
                'SOCIAL_MEDIA', 'https://www.facebook.com', 720)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            base_url = EXCLUDED.base_url,
            cache_ttl_hours = EXCLUDED.cache_ttl_hours
        """
    )


def downgrade() -> None:
    # Con consultas guardadas la fuente se conserva: borrarla perdería el historial.
    op.execute(
        """
        DELETE FROM simec.sources s
        WHERE s.code = 'FACEBOOK_PAGE'
          AND NOT EXISTS (SELECT 1 FROM simec.source_snapshots x WHERE x.source_id = s.id)
          AND NOT EXISTS (SELECT 1 FROM simec.source_cache c WHERE c.source_id = s.id)
        """
    )
