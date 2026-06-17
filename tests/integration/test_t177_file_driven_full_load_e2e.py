from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._t177_full_load_harness import (
    ENV_ALLOW_NONEMPTY,
    ENV_CONFIRM,
    T177PreflightError,
    T177SkipError,
    apply_schema_index_smoke,
    assert_no_existing_rows_without_confirmation,
    build_discovery_plan,
    collect_existing_row_counts,
    runtime_from_env,
    schema_smoke_report,
    validate_database_preflight,
    write_json_artifact,
)


@pytest.mark.asyncio
async def test_t177_file_driven_full_load_preflight_and_schema_smoke() -> None:
    started_at = datetime.now(UTC)
    try:
        runtime = runtime_from_env()
    except T177SkipError as exc:
        pytest.skip(str(exc))

    engine = make_async_engine(Settings(pg_dsn=runtime.dsn))
    try:
        preflight = await validate_database_preflight(
            engine,
            confirmation=os.getenv(ENV_CONFIRM),
        )
        discovery_plan = build_discovery_plan(runtime.data_root)

        await apply_schema_index_smoke(engine)
        schema_report = await schema_smoke_report(engine)
        existing_rows = await collect_existing_row_counts(engine)
        allow_nonempty = os.getenv(ENV_ALLOW_NONEMPTY) == "1"
        assert_no_existing_rows_without_confirmation(
            existing_rows,
            destructive_confirmed=preflight.destructive_confirmed,
            allow_nonempty=allow_nonempty,
        )

        artifact = {
            "schema_version": 1,
            "task": "T-177B",
            "run_id": runtime.run_id,
            "mode": "preflight_schema_smoke",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "gates": {
                "full_load_e2e": True,
                "pg_dsn": True,
                "confirmation_ok": preflight.destructive_confirmed,
                "allow_nonempty": allow_nonempty,
                "longrun": False,
            },
            "database": {
                "name": preflight.database_name,
                "expected_confirmation": preflight.expected_confirmation,
                "destructive_confirmed": preflight.destructive_confirmed,
                "available_extensions": preflight.available_extensions,
            },
            "data": discovery_plan,
            "schema": schema_report,
            "existing_rows": existing_rows,
        }
        artifact_path = write_json_artifact(
            runtime.artifact_dir,
            "t177b-preflight-schema-smoke.json",
            artifact,
        )

        assert artifact_path.is_file()
        assert schema_report["missing_objects"] == []
        assert discovery_plan["data_root"] == str(runtime.data_root)
    except T177PreflightError as exc:
        pytest.fail(str(exc))
    finally:
        await engine.dispose()
