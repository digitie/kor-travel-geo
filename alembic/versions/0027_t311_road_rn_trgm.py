"""T-311 road fallback trigram index on tl_sprd_manage

v2 geocode의 도로 fallback/보조 후보(``GeometryRepository.road_geometries``)는 매 요청
``tl_sprd_manage`` 전체(약 87.5만 행, heap 480MB)를 순차 스캔하며 행마다 정규화 식을 계산했다
(운영 warm 약 4.7초, cold 16초 — API statement_timeout 5초를 넘긴다). 정규화 도로명 식에 trigram
GIN 인덱스를 두면 후보 조건(도로명 부분 일치·앞부분 일치)을 인덱스로 찾을 수 있다. 식은
``infra/geometry_repo.py`` SQL의 ``regexp_replace(m.rn, '\\s+', '', 'g')``와 글자 그대로 같아야
planner가 인덱스를 쓴다.

일반 ``CREATE INDEX``(CONCURRENTLY 아님)다: ``tl_sprd_manage``는 SHP 적재만 쓰기하므로 빌드 동안
쓰기만 막히고 API 읽기는 막히지 않는다. 만든 뒤 ``ANALYZE``로 식 통계를 채워 LIKE 선택도 추정이
맞게 한다. fresh-init DDL(``src/kortravelgeo/infra/sql.py`` INDEX_SQL)과 ``sql/indexes.sql``에도
같은 정의가 있다.

Revision ID: 0027_t311_road_rn_trgm
Revises: 0026_t290k_retire_inproc
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0027_t311_road_rn_trgm"
down_revision = "0026_t290k_retire_inproc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    op.execute(
        r"""
CREATE INDEX IF NOT EXISTS idx_sprd_manage_rn_nrm_trgm
  ON tl_sprd_manage USING GIN ((regexp_replace(rn, '\s+', '', 'g')) gin_trgm_ops);
"""
    )
    op.execute("ANALYZE tl_sprd_manage")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sprd_manage_rn_nrm_trgm")
