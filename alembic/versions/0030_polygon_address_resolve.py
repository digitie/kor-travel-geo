"""건물 도형의 소재지 시군구 기준 주소 연결 인덱스.

원본 도로 관할 코드와 건물 소재지 코드가 다를 때도 주소 소재지 코드로
연결한다. 원본 rncode_full과 기존 인덱스는 보존한다. 일반 인덱스 생성은
API 읽기를 허용하며, 적재 작업이 종료된 유지보수 구간에 실행한다.
"""

from __future__ import annotations

from alembic import op

revision = "0030_polygon_address_resolve"
down_revision = "0029_t325a_data_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_spbd_buld_polygon_address_resolve "
        "ON public.tl_spbd_buld_polygon ((sig_cd || rn_cd), buld_se_cd, buld_mnnm, buld_slno, bjd_cd)"
    )
    op.execute("ANALYZE public.tl_spbd_buld_polygon")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.idx_spbd_buld_polygon_address_resolve")
