"""T-283 파일 관리: 통합 파일 인벤토리의 순수 판정/집계 로직 테스트 (DB-free).

``core.file_inventory``의 lifecycle 도출 규칙과 요약 집계,
``infra.file_inventory_repo``의 행→DTO 매핑(artifact)을 고정한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from kortravelgeo.core.file_inventory import (
    TEMPORARY_LIFECYCLES,
    SourceGroupFacts,
    build_inventory_summary,
    derive_artifact_lifecycle,
    derive_source_group_lifecycle,
    orphan_lifecycle,
)
from kortravelgeo.dto.admin import OpsArtifact
from kortravelgeo.dto.file_inventory import FileInventoryItem
from kortravelgeo.infra.file_inventory_repo import artifact_inventory_item

_NOW = datetime(2026, 7, 4, tzinfo=UTC)


def _facts(**overrides: object) -> SourceGroupFacts:
    base: dict[str, object] = {
        "group_state": "available",
        "session_state": "registered",
        "registered_at_present": True,
        "active_match_set_id": None,
        "match_set_count": 0,
    }
    base.update(overrides)
    return SourceGroupFacts(**base)  # type: ignore[arg-type]


class TestSourceGroupLifecycle:
    def test_active_match_set_is_serving_and_in_use(self) -> None:
        verdict = derive_source_group_lifecycle(
            _facts(active_match_set_id="ms-1", match_set_count=2)
        )
        assert verdict.lifecycle == "serving"
        assert verdict.in_use is True
        assert verdict.temporary is False

    def test_non_active_match_set_membership_is_staging(self) -> None:
        verdict = derive_source_group_lifecycle(_facts(match_set_count=1))
        assert verdict.lifecycle == "staging"
        assert verdict.in_use is False

    def test_unreferenced_available_group_is_idle(self) -> None:
        assert derive_source_group_lifecycle(_facts()).lifecycle == "idle"

    def test_non_terminal_session_is_in_progress_and_temporary(self) -> None:
        verdict = derive_source_group_lifecycle(
            _facts(group_state="validating", session_state="uploading",
                   registered_at_present=False)
        )
        assert verdict.lifecycle == "in_progress"
        assert verdict.temporary is True

    def test_registration_expired_without_register_is_unregistered(self) -> None:
        verdict = derive_source_group_lifecycle(
            _facts(session_state="registration_expired", registered_at_present=False)
        )
        assert verdict.lifecycle == "unregistered"
        assert verdict.temporary is True

    def test_group_terminal_states_win_over_usage(self) -> None:
        for state in ("quarantined", "missing", "soft_deleted", "hard_deleted"):
            verdict = derive_source_group_lifecycle(
                _facts(group_state=state, active_match_set_id="ms-1", match_set_count=1)
            )
            assert verdict.lifecycle == state
            assert verdict.in_use is False

    def test_delete_failed_is_temporary_cleanup_target(self) -> None:
        verdict = derive_source_group_lifecycle(_facts(group_state="delete_failed"))
        assert verdict.temporary is True
        assert verdict.lifecycle in TEMPORARY_LIFECYCLES


class TestArtifactAndOrphanLifecycle:
    def test_artifact_states(self) -> None:
        assert derive_artifact_lifecycle("creating").lifecycle == "creating"
        assert derive_artifact_lifecycle("creating").temporary is True
        assert derive_artifact_lifecycle("failed").temporary is True
        assert derive_artifact_lifecycle("available").lifecycle == "available"
        assert derive_artifact_lifecycle("available").temporary is False
        assert derive_artifact_lifecycle("expired").lifecycle == "expired"
        assert derive_artifact_lifecycle("deleted").lifecycle == "deleted"

    def test_orphan_is_temporary(self) -> None:
        verdict = orphan_lifecycle()
        assert verdict.lifecycle == "orphan"
        assert verdict.temporary is True

    def test_artifact_item_mapping(self) -> None:
        artifact = OpsArtifact(
            artifact_id="art-1",
            artifact_type="db_backup",
            state="available",
            storage_kind="local_file",
            storage_uri="file:///data/backups/a.tar.zst",
            display_name="kor_travel_geo-20260701.tar.zst",
            size_bytes=1024,
            retention_class="scheduled",
            job_id="job-1",
            created_at=_NOW,
            finished_at=_NOW,
        )
        item = artifact_inventory_item(artifact)
        assert item.file_kind == "artifact"
        assert item.id == "art-1"
        assert item.category == "db_backup"
        assert item.lifecycle == "available"
        assert item.storage_ref == "file:///data/backups/a.tar.zst"
        assert item.acquired_at == _NOW
        assert item.job_id == "job-1"
        assert item.detail["retention_class"] == "scheduled"


class TestInventorySummary:
    def test_summary_counts(self) -> None:
        items = (
            FileInventoryItem(
                file_kind="source_group",
                id="g1",
                name="도로명주소 한글 전체분",
                category="roadname_hangul_full",
                state="available",
                lifecycle="serving",
                in_use=True,
                temporary=False,
                size_bytes=100,
                open_issue_count=2,
            ),
            FileInventoryItem(
                file_kind="artifact",
                id="a1",
                name="backup.tar.zst",
                category="db_backup",
                state="creating",
                lifecycle="creating",
                in_use=False,
                temporary=True,
                size_bytes=None,
            ),
            FileInventoryItem(
                file_kind="orphan_object",
                id="o1",
                name="sources/x.zip",
                category="rustfs_object",
                state="object_missing_db",
                lifecycle="orphan",
                in_use=False,
                temporary=True,
                size_bytes=50,
            ),
        )
        summary = build_inventory_summary(items)
        assert summary.total_count == 3
        assert summary.total_bytes == 150
        assert summary.in_use_count == 1
        assert summary.temporary_count == 2
        assert summary.open_issue_count == 2
        assert summary.by_lifecycle == {"serving": 1, "creating": 1, "orphan": 1}
        assert summary.by_kind == {
            "source_group": 1,
            "artifact": 1,
            "orphan_object": 1,
        }
