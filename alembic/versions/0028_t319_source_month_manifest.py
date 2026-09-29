"""T-319 원천 기준월 load_manifest backfill

serving release 기록(``admin_repo._infer_current_source_set``)과 백업 manifest
(``backup.infer_source_set``)는 원천 테이블마다 ``SELECT max(source_yyyymm)``을 돌렸다.
``source_yyyymm`` 인덱스가 없어 매번 parallel seq scan이었다(운영 2026-09-28: 백업 preflight
11분, MV refresh 끝단 수 분). T-319부터 두 곳은 ``load_manifest.source_yyyymm``만 읽고, 행이
없으면 scan하지 않고 "모름"(None)으로 둔다. 적재기는 이제 적재할 때마다 이 행을 남긴다.

T-319 이전에 적재한 DB에는 도로명주소 한글(``tl_juso_text``)·위치정보요약·내비게이션 건물·SHP
건물 polygon 테이블의 manifest 행이 없다(적재기가 쓰지 않았다). 그대로 두면 다음 release부터
그 기준월이 빠지므로, manifest 행이 **없는** 테이블에 한해 여기서 딱 한 번 옛 조회와 같은 exact
값(``max(source_yyyymm)``, 행 수는 ``count(*)``)을 계산해 채운다.

- manifest 행이 이미 있는 테이블(적재기가 쓴 값)은 건드리지도 scan하지도 않는다 — ``NOT
  EXISTS``가 scan 위의 one-time filter라 거짓이면 scan 노드가 실행되지 않는다.
- 예외: ``tl_juso_text``의 일변동 행(``source_set.kind = 'daily_juso_delta'``). T-319 이전에는
  일변동(``daily_juso_loader._upsert_manifest``)만 이 행을 쓰고 전체분 적재기는 갱신하지
  않았다 — 일변동 뒤에 더 새 전체분을 적재한 DB는 옛 월을 들고 있다. 이 행은 믿지 않고 scan해
  ``source_yyyymm``만 ``GREATEST(기존, max)``로 올린다. 일변동 watermark(``last_delta_at``·
  ``last_mvmn_de``)와 ``source_set``은 그대로 둔다(그래서 downgrade도 이 행은 지우지 않는다).
- 빈 테이블은 건너뛴다(옛 조회도 NULL이었고, 조회는 행이 없으면 None이다).

비용은 manifest가 없는 테이블마다 seq scan 1회다. 운영(2026-09) 기준 heap
``tl_juso_text`` 1.8GB·``tl_locsum_entrc`` 1.6GB·``tl_navi_buld_centroid`` 2.9GB·
``tl_spbd_buld_polygon`` 3.6GB — MV refresh와 백업이 매번 하던 scan을 배포 때 한 번 한다.
fresh DB(``ktgctl init-db`` + ``alembic stamp head``)는 테이블이 비어 있어 할 일이 없다.

Revision ID: 0028_t319_source_month_manifest
Revises: 0027_t311_road_rn_trgm
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0028_t319_source_month_manifest"
down_revision = "0027_t311_road_rn_trgm"
branch_labels = None
depends_on = None

#: ``infra.admin_repo._infer_current_source_set``가 읽는 원천 테이블(백업은 이 중 6개).
SOURCE_MONTH_TABLES = (
    "tl_juso_text",
    "tl_juso_parcel_link",
    "tl_locsum_entrc",
    "tl_navi_buld_centroid",
    "tl_spbd_buld_polygon",
    "tl_roadaddr_entrc",
    "tl_sppn_makarea",
)

BACKFILL_KIND = "t319_backfill"

#: 행이 있어도 테이블 기준월로 믿지 않는 manifest kind(위 docstring의 예외).
UNTRUSTED_MANIFEST_KIND = {"tl_juso_text": "daily_juso_delta"}


def backfill_sql(table_name: str) -> str:
    gate = f"SELECT 1 FROM load_manifest WHERE table_name = '{table_name}'"
    on_conflict = "DO NOTHING"
    untrusted_kind = UNTRUSTED_MANIFEST_KIND.get(table_name)
    if untrusted_kind is not None:
        gate += f" AND source_set ->> 'kind' IS DISTINCT FROM '{untrusted_kind}'"
        on_conflict = f"""DO UPDATE SET
  source_yyyymm = GREATEST(load_manifest.source_yyyymm, EXCLUDED.source_yyyymm),
  updated_at = now()
 WHERE load_manifest.source_set ->> 'kind' = '{untrusted_kind}'"""
    return f"""
INSERT INTO load_manifest (table_name, row_count, source_yyyymm, source_set, updated_at)
SELECT '{table_name}', count(*), max(source_yyyymm),
       jsonb_build_object('kind', '{BACKFILL_KIND}'), now()
  FROM public.{table_name}
 WHERE NOT EXISTS ({gate})
HAVING count(*) > 0
ON CONFLICT (table_name) {on_conflict}
"""


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    for table_name in SOURCE_MONTH_TABLES:
        op.execute(backfill_sql(table_name))


def downgrade() -> None:
    op.execute(f"DELETE FROM load_manifest WHERE source_set ->> 'kind' = '{BACKFILL_KIND}'")
