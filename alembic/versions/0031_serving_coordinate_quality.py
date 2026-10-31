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
    # 판정 이력과 게시 중인 MV의 의존성을 보존한다. 이전 코드는 추가 테이블을 무시한다.
    # 원천으로 MV를 재생성하면 격리했던 좌표가 다시 노출되므로 여기서 재생성하지 않는다.
    pass
