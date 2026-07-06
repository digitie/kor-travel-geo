"""File-inventory lifecycle derivation (T-283 파일 관리).

Pure decision logic for the unified stored-file inventory (`/v1/admin/storage/files`):
given facts about a source file group (or a backup/ops artifact), derive a single
`lifecycle` bucket plus the `in_use` / `temporary` flags the admin UI filters on.
DB-free by design — the repository maps rows to these facts and the API composes
the results (mirrors ``core.source_janitor``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from kortravelgeo.dto.file_inventory import FileInventoryItem, FileInventorySummary
from kortravelgeo.dto.source import TERMINAL_UPLOAD_SESSION_STATES

#: Unified lifecycle buckets across source groups / artifacts / orphan objects.
FileLifecycle = Literal[
    # source groups
    "serving",  # 활성 매칭 세트에 포함 — 서빙 구성에 사용 중
    "staging",  # 매칭 세트에는 포함되나 활성 세트는 아님
    "idle",  # 등록·검증 완료지만 어떤 매칭 세트도 참조하지 않음
    "in_progress",  # 업로드/검증 진행 중
    "unregistered",  # 저장은 됐지만 등록 기한이 지난 임시 상태
    "quarantined",
    "missing",
    "soft_deleted",
    "hard_deleted",
    "delete_failed",
    # artifacts
    "available",
    "creating",
    "failed",
    "expired",
    "deleted",
    # reconcile orphan objects (RustFS에만 존재)
    "orphan",
]

_GROUP_TERMINAL_STATES: frozenset[str] = frozenset(
    {"quarantined", "missing", "soft_deleted", "hard_deleted", "delete_failed"}
)

#: lifecycle 값 중 "임시/정리 대상" 성격 — UI의 임시 필터 기준.
TEMPORARY_LIFECYCLES: frozenset[str] = frozenset(
    {"in_progress", "unregistered", "creating", "failed", "orphan", "delete_failed"}
)


@dataclass(frozen=True, slots=True)
class SourceGroupFacts:
    """Row-level facts needed to classify one ``ops.source_file_groups`` entry."""

    group_state: str
    session_state: str | None
    registered_at_present: bool
    active_match_set_id: str | None
    match_set_count: int
    candidate_match_set_count: int


@dataclass(frozen=True, slots=True)
class LifecycleVerdict:
    lifecycle: str
    in_use: bool
    temporary: bool


def derive_source_group_lifecycle(facts: SourceGroupFacts) -> LifecycleVerdict:
    """Classify a source file group into one lifecycle bucket.

    우선순위: 그룹 터미널 상태(격리/삭제 등) > 진행 중 세션 > 등록 만료 >
    매칭 세트 사용 여부. ``in_use``는 활성 매칭 세트 포함 여부만 본다(서빙 기준).
    """

    in_use = facts.active_match_set_id is not None

    if facts.group_state in _GROUP_TERMINAL_STATES:
        return LifecycleVerdict(
            facts.group_state,
            in_use=False,
            temporary=facts.group_state == "delete_failed",
        )

    session_active = (
        facts.session_state is not None
        and facts.session_state not in TERMINAL_UPLOAD_SESSION_STATES
    )
    if session_active or facts.group_state == "validating":
        return LifecycleVerdict("in_progress", in_use=in_use, temporary=True)

    if facts.session_state == "registration_expired" and not facts.registered_at_present:
        return LifecycleVerdict("unregistered", in_use=False, temporary=True)

    if in_use:
        return LifecycleVerdict("serving", in_use=True, temporary=False)
    if facts.candidate_match_set_count > 0:
        return LifecycleVerdict("staging", in_use=False, temporary=False)
    return LifecycleVerdict("idle", in_use=False, temporary=False)


def derive_artifact_lifecycle(state: str) -> LifecycleVerdict:
    """Classify an ``ops.artifacts`` row (backup 등 산출물 파일)."""

    if state == "creating":
        return LifecycleVerdict("creating", in_use=False, temporary=True)
    if state == "failed":
        return LifecycleVerdict("failed", in_use=False, temporary=True)
    if state in {"expired", "deleted"}:
        return LifecycleVerdict(state, in_use=False, temporary=False)
    return LifecycleVerdict("available", in_use=False, temporary=False)


def orphan_lifecycle() -> LifecycleVerdict:
    """RustFS에는 있으나 DB 레지스트리에 없는 객체 (reconcile open issue)."""

    return LifecycleVerdict("orphan", in_use=False, temporary=True)


def build_inventory_summary(items: Sequence[FileInventoryItem]) -> FileInventorySummary:
    """목록에서 UI 상단 요약(개수·용량·사용/임시/이슈 카운트)을 집계한다."""

    by_lifecycle: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    total_bytes = 0
    in_use_count = 0
    temporary_count = 0
    open_issue_count = 0
    for item in items:
        by_lifecycle[item.lifecycle] = by_lifecycle.get(item.lifecycle, 0) + 1
        by_kind[item.file_kind] = by_kind.get(item.file_kind, 0) + 1
        total_bytes += item.size_bytes or 0
        if item.in_use:
            in_use_count += 1
        if item.temporary:
            temporary_count += 1
        open_issue_count += item.open_issue_count
    return FileInventorySummary(
        total_count=len(items),
        total_bytes=total_bytes,
        in_use_count=in_use_count,
        temporary_count=temporary_count,
        open_issue_count=open_issue_count,
        by_lifecycle=by_lifecycle,
        by_kind=by_kind,
    )
