"""T-325a dataset snapshot data_fingerprint (ADR-069 D1)

활성 serving release마다 v2 응답을 만드는 표(``infra/data_fingerprint.py``
``DATA_FINGERPRINT_TABLES``)의 내용 지문을 저장할 열이다. 외부 ``data_token``은
``"dd1-" + sha256(data_fingerprint)[:32]``로 여기서 파생한다(``core/dataset_version.py``).

NULL 허용이다 — 이력 행은 NULL로 두고(지문을 사후에 계산할 수 없다), 활성 릴리스 1건만
``ktgctl serving fingerprint-active``로 backfill한다(ADR-069 D9). 지문 계산이 실패한 활성화도
NULL로 통과한다(fail-open, D5). 열 추가만이라 테이블 재작성·scan이 없다.

fresh-init DDL(``src/kortravelgeo/infra/sql.py``)과 ``sql/ddl/001_schema.sql``에도 같은 열이 있다.

revision id는 ADR-069 D1이 적은 ``0029_t325a_dataset_data_fingerprint``(35자)가 아니라 이것이다 —
``alembic_version.version_num``이 ``varchar(32)``라 35자는 stamp/upgrade에서 잘린다.

Revision ID: 0029_t325a_data_fingerprint
Revises: 0028_t319_source_month_manifest
Create Date: 2026-10-13
"""

from __future__ import annotations

from alembic import op

revision = "0029_t325a_data_fingerprint"
down_revision = "0028_t319_source_month_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ops.dataset_snapshots ADD COLUMN IF NOT EXISTS data_fingerprint TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE ops.dataset_snapshots DROP COLUMN IF EXISTS data_fingerprint")
