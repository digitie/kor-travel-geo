"""정확 도로명주소의 도로명·본번·부번·지하 여부를 함께 찾는다."""

from __future__ import annotations

from alembic import op

from kortravelgeo.infra.sql import ROAD_ADDRESS_INDEX_SQL

revision = "0032_road_address_exact_index"
down_revision = "0031_serving_coordinate_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 일반 인덱스 생성은 MV의 읽기를 허용한다. 게시·refresh와 겹치면 빠르게 실패한다.
    # text_pattern_ops는 기존 동등 비교를 지원하며 긴 로케일 문자열 정렬을 피한다.
    op.execute("SET LOCAL search_path = public, x_extension")
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '15min'")
    op.execute("SET LOCAL maintenance_work_mem = '64MB'")
    op.execute("SET LOCAL max_parallel_maintenance_workers = 0")
    op.execute(ROAD_ADDRESS_INDEX_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.idx_mv_road_address_exact")
