"""T-312: app role(비-superuser) ``pg_restore``를 공용 instance에서 성립시키는 TOC 필터.

공용 PostgreSQL instance(T-308)에서는 cluster admin이 DB마다 ``x_extension`` schema와
postgis/pg_trgm/unaccent/pg_stat_statements extension을 미리 만들고, app role에는 그 schema의
``USAGE``만 준다. app role로 찍은 ADR-030 directory dump에도 그 schema/extension의 TOC entry가
그대로 들어 있어, app role이 ``pg_restore --clean --if-exists``로 복원하면 다음이 실패한다
(PG16 실측):

- ``EXTENSION``/``COMMENT - EXTENSION`` — ``must be owner of extension``
- ``SCHEMA - x_extension`` — ``must be owner of schema`` (drop) / ``already exists`` (create)
- ``TABLE DATA x_extension spatial_ref_sys`` — ``permission denied`` (postgis config table)
- 전용 instance 시절 백업의 ``ALTER ... OWNER TO <옛 owner>``/``GRANT ... TO <없는 role>``

복원 대상 DB에서 현재 role이 관리할 수 없는(소유하지 않은) extension과, 그런 extension이 사는
admin 소유 schema를 조회해(:data:`RESTORE_TARGET_ROLE_SQL`) 해당 entry를 ``pg_restore --use-list``
에서 주석 처리하고, 비-superuser면 ``--no-owner --no-privileges``로 복원한다. superuser 복원
(전용 instance·dev·테스트)은 ``pg_has_role``이 항상 참이라 필터가 비고 기존과 같다.

``public``/``pg_catalog``는 extension이 살더라도 절대 schema 단위로 거르지 않는다 — 거르면
serving 테이블 전체가 조용히 빠진다.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "RESTORE_TARGET_ROLE_SQL",
    "PreprovisionedTocFilter",
    "RestoreTargetRole",
    "filter_preprovisioned_toc",
]

#: 복원 대상 DB에서 현재 role의 superuser 여부 + 관리 불가 extension/extension schema.
#: ``pg_has_role(owner, 'USAGE')``는 superuser면 항상 참이므로 superuser는 두 배열이 빈다.
RESTORE_TARGET_ROLE_SQL: Final = """
SELECT r.rolsuper AS is_superuser,
       ARRAY(
           SELECT e.extname::text
             FROM pg_extension e
            WHERE NOT pg_has_role(e.extowner, 'USAGE')
            ORDER BY 1
       ) AS extensions,
       ARRAY(
           SELECT DISTINCT n.nspname::text
             FROM pg_extension e
             JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE NOT pg_has_role(e.extowner, 'USAGE')
              AND NOT pg_has_role(n.nspowner, 'USAGE')
              AND n.nspname NOT IN ('public', 'pg_catalog')
            ORDER BY 1
       ) AS schemas
  FROM pg_roles r
 WHERE r.rolname = current_user
"""

_NEVER_FILTERED_SCHEMAS: Final = frozenset({"public", "pg_catalog"})

#: ``pg_restore -l`` 한 줄: ``<dumpId>; <tableoid> <oid> <desc> <namespace|-> <tag> <owner>``.
_TOC_ENTRY_RE: Final = re.compile(r"^\s*\d+; \d+ \d+ (?P<rest>.*)$")


@dataclass(frozen=True, slots=True)
class RestoreTargetRole:
    """복원 대상 DB에서 본 현재 role (:data:`RESTORE_TARGET_ROLE_SQL` 결과)."""

    is_superuser: bool
    unmanaged_extensions: tuple[str, ...] = ()
    unmanaged_extension_schemas: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreprovisionedTocFilter:
    """``--use-list``로 쓸 줄과, 주석 처리해 건너뛴 TOC entry."""

    lines: tuple[str, ...] = ()
    skipped_entries: tuple[str, ...] = ()


def filter_preprovisioned_toc(
    toc_lines: Sequence[str],
    *,
    extensions: Collection[str],
    schemas: Collection[str],
) -> PreprovisionedTocFilter:
    """대상 DB에 미리 만들어진 extension/extension schema의 TOC entry를 주석 처리한다 (pure).

    건너뛰는 entry:

    - ``EXTENSION - <ext>``, ``COMMENT - EXTENSION <ext>`` (``ext`` ∈ ``extensions``)
    - ``SCHEMA - <schema>``, ``ACL - SCHEMA <schema>``, ``COMMENT - SCHEMA <schema>``
    - namespace가 ``<schema>``인 모든 entry (예: ``TABLE DATA x_extension spatial_ref_sys``) —
      admin 소유 schema라 app role은 거기에 객체를 만들거나 행을 넣을 수 없다.

    ``public``/``pg_catalog``는 ``schemas``에 있어도 무시한다. 주석/빈 줄과 나머지 entry는
    그대로 둔다 (``--use-list``는 ``;``로 시작하는 줄을 건너뛴다).
    """
    schema_names = [s for s in schemas if s not in _NEVER_FILTERED_SCHEMAS]
    extension_prefixes = tuple(
        prefix
        for ext in extensions
        for prefix in (f"EXTENSION - {ext} ", f"COMMENT - EXTENSION {ext} ")
    )
    schema_prefixes = tuple(
        prefix
        for schema in schema_names
        for prefix in (
            f"SCHEMA - {schema} ",
            f"ACL - SCHEMA {schema} ",
            f"COMMENT - SCHEMA {schema} ",
        )
    )
    # desc는 대문자 단어(예: "TABLE DATA", "SEQUENCE SET"), 그 다음 토큰이 namespace다.
    in_schema = tuple(re.compile(rf"[A-Z][A-Z ]* {re.escape(s)} ") for s in schema_names)

    out: list[str] = []
    skipped: list[str] = []
    for line in toc_lines:
        match = _TOC_ENTRY_RE.match(line)
        if match is None:
            out.append(line)
            continue
        # owner가 비는 entry(EXTENSION 등)도 같은 경계로 비교하도록 끝 공백을 하나로 맞춘다.
        rest = match.group("rest").rstrip() + " "
        if rest.startswith(extension_prefixes + schema_prefixes) or any(
            pattern.match(rest) for pattern in in_schema
        ):
            out.append(f";{line}")
            skipped.append(line.strip())
        else:
            out.append(line)
    return PreprovisionedTocFilter(lines=tuple(out), skipped_entries=tuple(skipped))
