"""원천 보존·서빙 격리와 검증된 대체 좌표 판정 이력."""

from __future__ import annotations

from alembic import op

from kortravelgeo.infra.serving_quality import QUALITY_DDL

revision = "0031_serving_coordinate_quality"
down_revision = "0030_polygon_address_resolve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = public, x_extension")
    for statement in QUALITY_DDL:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.serving_coordinate_quarantine")
    op.execute("DROP TABLE IF EXISTS public.serving_quality_runs")
