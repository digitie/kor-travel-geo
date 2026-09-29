"""Load manifest models and checksums."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import psycopg

#: T-319: 전체분 upsert 적재기가 적재를 마치며 같은 transaction에서 남기는 테이블 기준월.
#: serving release 기록·백업 manifest(``infra.admin_repo.source_yyyymm_by_kind``)가 원천
#: 테이블을 ``max(source_yyyymm)``로 전수 scan하지 않고 이 행을 읽는다. 다른 manifest
#: writer(지번·출입구·일변동·구역)와 같이 마지막 적재가 이긴다. ``source_zip``/
#: ``source_checksum``은 이전 일변동의 값이 이번 적재를 설명하는 것처럼 남지 않게 비운다
#: (``last_delta_at``/``last_mvmn_de``는 일변동 watermark라 그대로 둔다).
FULL_LOAD_SOURCE_MONTH_SQL = """
INSERT INTO load_manifest (
  table_name, last_full_load_at, row_count, source_yyyymm, source_set, updated_at
) VALUES (
  %(table_name)s, now(), %(row_count)s, %(source_yyyymm)s, %(source_set)s::jsonb, now()
)
ON CONFLICT (table_name) DO UPDATE SET
  last_full_load_at = EXCLUDED.last_full_load_at,
  row_count = EXCLUDED.row_count,
  source_zip = NULL,
  source_checksum = NULL,
  source_yyyymm = EXCLUDED.source_yyyymm,
  source_set = EXCLUDED.source_set,
  updated_at = now()
"""


#: T-323: 전체 재적재가 테이블을 비울 때(SHP·구역 ``TRUNCATE``) manifest 행을 지우지 않고 기준월만
#: "모름"(NULL)으로 둔다. 행을 지우면 ``source_yyyymm_by_kind``가 manifest 없는 legacy 테이블로 보고
#: active release의 이전 기준월로 메우는데, 재적재가 TRUNCATE 뒤에 실패하면 새 달 행이 섞인 테이블에
#: 옛 달이 붙는다. NULL 행은 그대로 "모름"으로 읽힌다. 적재가 끝나면 각 적재기의 manifest writer가
#: 새 달로 덮는다. 행이 없던 테이블(0028 이전 legacy)에는 새 행을 만들지 않는다.
#: SQLAlchemy ``text()``용.
TRUNCATED_SOURCE_MONTH_SQL = """
UPDATE load_manifest
   SET source_yyyymm = NULL,
       row_count = 0,
       source_set = jsonb_build_object('kind', 'truncated_for_full_load'),
       updated_at = now()
 WHERE table_name = ANY(:table_names)
"""


@dataclass(frozen=True, slots=True)
class LoadManifest:
    table_name: str
    source_path: Path
    source_yyyymm: str | None
    source_checksum: str
    row_count: int = 0


def max_source_yyyymm(current: str | None, value: str | None) -> str | None:
    """``max(source_yyyymm)``처럼 NULL을 건너뛴 최댓값(적재 row를 흘려보내며 누적한다)."""
    if value is None:
        return current
    return value if current is None or value > current else current


async def record_full_load_source_month(
    cur: psycopg.AsyncCursor[Any],
    *,
    table_name: str,
    kind: str,
    row_count: int,
    source_yyyymm: str | None,
) -> None:
    """``FULL_LOAD_SOURCE_MONTH_SQL`` 실행. 적재 row가 0건이면 테이블이 그대로이므로 남기지
    않는다(호출자가 판단) — ``source_yyyymm``은 이번 적재 row들의 최댓값이다."""
    await cur.execute(
        FULL_LOAD_SOURCE_MONTH_SQL,
        {
            "table_name": table_name,
            "row_count": row_count,
            "source_yyyymm": source_yyyymm,
            "source_set": json.dumps({"kind": kind, "processed_rows": row_count}),
        },
    )


def infer_yyyymm(path: Path | str) -> str | None:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", str(path))
    return "".join(match.groups()) if match else None


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

