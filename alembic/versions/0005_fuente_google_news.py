"""Agrega Google News al catálogo de fuentes.

Si la API ya registró la fuente sola (queda como UNCLASSIFIED), se completan sus datos.
Vigencia de 1 día: solo marca `is_stale`; nunca re-consulta.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO simec.sources (code, name, category, base_url, cache_ttl_hours)
        VALUES ('GOOGLE_NEWS_RSS', 'Google News - Noticias por nombre o tema (RSS)',
                'NEWS', 'https://news.google.com', 24)
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
        WHERE s.code = 'GOOGLE_NEWS_RSS'
          AND NOT EXISTS (SELECT 1 FROM simec.source_snapshots x WHERE x.source_id = s.id)
          AND NOT EXISTS (SELECT 1 FROM simec.source_cache c WHERE c.source_id = s.id)
        """
    )
