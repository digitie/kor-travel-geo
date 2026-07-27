from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.exceptions import InvalidInputError
from scripts import benchmark_backup_restore as bench

if TYPE_CHECKING:
    from pathlib import Path


def test_default_matrix_covers_profiles_jobs_and_compression() -> None:
    plan = bench.build_matrix()

    assert len(plan) == 27
    assert {item.profile for item in plan} == {"serving-ready", "lean-serving", "forensic"}
    assert {item.jobs for item in plan} == {1, 2, 4}
    assert {item.compression_level for item in plan} == {3, 9, 19}
    assert plan[0].profile_id == "serving_ready_j1_z3"
    assert all(len(item.target_database) <= 63 for item in plan)


def test_execute_requires_typed_confirmation() -> None:
    with pytest.raises(ValueError, match="RUN-T247-BENCHMARK kor_travel_geo"):
        bench.validate_execute_confirmation(
            execute=True,
            database="kor_travel_geo",
            confirmation=None,
        )

    bench.validate_execute_confirmation(
        execute=True,
        database="kor_travel_geo",
        confirmation="RUN-T247-BENCHMARK kor_travel_geo",
    )
    bench.validate_execute_confirmation(
        execute=False,
        database="kor_travel_geo",
        confirmation=None,
    )


def test_plan_only_main_writes_report_and_summary(tmp_path: Path) -> None:
    assert bench.main(["--run-id", "t247-plan-test", "--output-dir", str(tmp_path)]) == 0

    report = json.loads((tmp_path / "benchmark-report.json").read_text(encoding="utf-8"))
    plan = json.loads((tmp_path / "matrix-plan.json").read_text(encoding="utf-8"))
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")

    assert report["schema_version"] == 1
    assert report["task_id"] == "T-247"
    assert report["mode"] == "plan"
    assert report["results"] == []
    assert len(report["plan"]) == 27
    assert len(plan) == 27
    assert "계획 전용 실행" in summary
    assert "N150/Odroid 해석 가이드" in summary


def test_summarize_results_picks_fastest_and_smallest_archive() -> None:
    results = (
        _result(
            "serving_ready_j1_z3",
            jobs=1,
            compression=3,
            backup=10.0,
            restore=20.0,
            dump_bytes=1_000,
            archive_bytes=500,
        ),
        _result(
            "serving_ready_j2_z9",
            jobs=2,
            compression=9,
            backup=8.0,
            restore=15.0,
            dump_bytes=1_000,
            archive_bytes=300,
        ),
        _result(
            "serving_ready_j4_z19",
            jobs=4,
            compression=19,
            backup=30.0,
            restore=12.0,
            dump_bytes=1_000,
            archive_bytes=250,
        ),
    )

    summary = bench.summarize_results(results)

    assert len(summary) == 1
    row = summary[0]
    assert row.fastest_total_profile_id == "serving_ready_j2_z9"
    assert row.fastest_backup_profile_id == "serving_ready_j2_z9"
    assert row.fastest_restore_profile_id == "serving_ready_j4_z19"
    assert row.smallest_archive_profile_id == "serving_ready_j4_z19"
    assert row.best_compression_ratio_profile_id == "serving_ready_j4_z19"
    assert "총 소요시간 최단" in row.low_power_note


def test_plan_only_main_refuses_colliding_target_prefix(tmp_path: Path) -> None:
    dsn = "postgresql+psycopg://user:pass@localhost:5432/boom_serving_ready_j1_z3"

    with pytest.raises(InvalidInputError, match="must differ from the current database"):
        bench.main(
            [
                "--pg-dsn",
                dsn,
                "--target-prefix",
                "boom",
                "--profile",
                "serving-ready",
                "--jobs",
                "1",
                "--compression-level",
                "3",
                "--output-dir",
                str(tmp_path),
            ]
        )


def test_build_matrix_refuses_target_matching_current_database() -> None:
    plan = bench.build_matrix(
        profiles=("serving-ready",),
        jobs=(1,),
        compression_levels=(3,),
        target_prefix="x",
    )
    colliding_target = plan[0].target_database

    with pytest.raises(InvalidInputError, match="must differ from the current database"):
        bench.build_matrix(
            profiles=("serving-ready",),
            jobs=(1,),
            compression_levels=(3,),
            target_prefix="x",
            current_database=colliding_target,
        )


async def test_drop_database_refuses_to_drop_operational_database(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    async def fake_admin_exec(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(bench, "_admin_exec", fake_admin_exec)
    dsn = "postgresql+psycopg://user:pass@localhost:5432/kor_travel_geo"

    with pytest.raises(InvalidInputError, match="must differ from the current database"):
        await bench.drop_database(dsn, "kor_travel_geo")

    assert calls == []


async def test_drop_database_forwards_connect_timeout_to_admin_exec(monkeypatch) -> None:
    calls: list[int] = []

    async def fake_admin_exec(
        dsn: str,
        statement: str,
        params: dict[str, object] | None = None,
        *,
        connect_timeout_s: int = 10,
    ) -> None:
        _ = (dsn, statement, params)
        calls.append(connect_timeout_s)

    monkeypatch.setattr(bench, "_admin_exec", fake_admin_exec)
    dsn = "postgresql+psycopg://user:pass@localhost:5432/kor_travel_geo"

    await bench.drop_database(dsn, "kor_travel_geo_other", connect_timeout_s=42)

    assert calls == [42, 42]


async def test_create_database_forwards_connect_timeout_to_admin_exec(monkeypatch) -> None:
    calls: list[int] = []

    async def fake_admin_exec(
        dsn: str,
        statement: str,
        params: dict[str, object] | None = None,
        *,
        connect_timeout_s: int = 10,
    ) -> None:
        _ = (dsn, statement, params)
        calls.append(connect_timeout_s)

    monkeypatch.setattr(bench, "_admin_exec", fake_admin_exec)
    dsn = "postgresql+psycopg://user:pass@localhost:5432/kor_travel_geo"

    await bench.create_database(dsn, "kor_travel_geo_other", connect_timeout_s=42)

    assert calls == [42]


async def test_admin_exec_preserves_password_in_maintenance_dsn(monkeypatch) -> None:
    """#299 후속(적대적 리뷰 발견): infra/backup.py의 cleanup_orphan_restore_target과
    동일한 str(url) 비밀번호 마스킹 버그가 이 스크립트의 _admin_exec에도 그대로
    있었다(#298 자체 수정에서 놓침) — 실제 비밀번호 DSN에서는 create_database/
    drop_database가 매번 인증 실패로 죽는다."""
    captured_dsns: list[str] = []

    class _FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

        async def execute(self, *args, **kwargs) -> None:
            return None

    class _FakeEngine:
        def connect(self):
            return _FakeConnection()

        async def dispose(self) -> None:
            return None

    def fake_create_async_engine(dsn, **kwargs):
        captured_dsns.append(dsn)
        return _FakeEngine()

    monkeypatch.setattr(bench, "create_async_engine", fake_create_async_engine)

    await bench._admin_exec(
        "postgresql+psycopg://addr:s3cr3t_pw@localhost:5432/kor_travel_geo",
        "SELECT 1",
    )

    assert len(captured_dsns) == 1
    assert "s3cr3t_pw" in captured_dsns[0]
    assert "***" not in captured_dsns[0]


def test_invalid_jobs_exits_cleanly_instead_of_raw_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        bench.main(["--jobs", "999", "--output-dir", str(tmp_path)])

    assert exc_info.value.code == 2
    assert "jobs must be between 1 and 64" in capsys.readouterr().err


def test_invalid_compression_level_exits_cleanly_instead_of_raw_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        bench.main(["--compression-level", "99", "--output-dir", str(tmp_path)])

    assert exc_info.value.code == 2
    assert "compression level must be between 1 and 19" in capsys.readouterr().err


def _result(
    profile_id: str,
    *,
    jobs: int,
    compression: int,
    backup: float,
    restore: float,
    dump_bytes: int,
    archive_bytes: int,
) -> bench.BackupRestoreResult:
    return bench.BackupRestoreResult(
        profile_id=profile_id,
        profile="serving-ready",
        jobs=jobs,
        compression_level=compression,
        target_database=f"target_{profile_id}",
        ok=True,
        error=None,
        artifact_id=f"artifact_{profile_id}",
        archive_path=f"/tmp/{profile_id}.tar.zst",
        backup_seconds=backup,
        restore_seconds=restore,
        size_probe_seconds=1.0,
        dump_bytes=dump_bytes,
        archive_bytes=archive_bytes,
        compression_ratio=round(dump_bytes / archive_bytes, 4),
        archive_to_dump_ratio=round(archive_bytes / dump_bytes, 4),
    )
