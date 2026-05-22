from kraddr.geo.infra.load_jobs import (
    CREATE_LOAD_JOBS_STATE_INDEX_SQL,
    CREATE_LOAD_JOBS_TABLE_SQL,
    MARK_INTERRUPTED_RUNNING_FAILED_SQL,
    LoadJobState,
    decide_startup_recovery,
)


def _squashed_sql(sql: object) -> str:
    return " ".join(str(sql).split())


def test_load_jobs_schema_contains_persistent_state_columns_and_constraints() -> None:
    sql = _squashed_sql(CREATE_LOAD_JOBS_TABLE_SQL)

    assert "CREATE TABLE IF NOT EXISTS load_jobs" in sql
    assert "job_id UUID PRIMARY KEY" in sql
    assert "payload JSONB NOT NULL" in sql
    assert "state TEXT NOT NULL CHECK" in sql
    assert "'PENDING','RUNNING','SUCCESS','FAILED','CANCELLED'" in sql
    assert "progress NUMERIC(5,4) NOT NULL DEFAULT 0" in sql
    assert "error_message TEXT" in sql
    assert "heartbeat_at TIMESTAMPTZ" in sql


def test_load_jobs_schema_has_state_created_index() -> None:
    sql = _squashed_sql(CREATE_LOAD_JOBS_STATE_INDEX_SQL)

    assert "CREATE INDEX IF NOT EXISTS idx_load_jobs_state_created" in sql
    assert "ON load_jobs (state, created_at)" in sql


def test_mark_interrupted_running_jobs_sql_only_touches_running_jobs() -> None:
    sql = _squashed_sql(MARK_INTERRUPTED_RUNNING_FAILED_SQL)

    assert "UPDATE load_jobs" in sql
    assert "SET state = 'FAILED'" in sql
    assert "COALESCE(error_message, :error_message)" in sql
    assert "WHERE state = 'RUNNING'" in sql
    assert "WHERE state IN" not in sql


def test_startup_recovery_marks_running_as_failed() -> None:
    decision = decide_startup_recovery(LoadJobState.RUNNING)

    assert decision.state is LoadJobState.FAILED
    assert decision.should_enqueue is False
    assert decision.error_message is not None
    assert "running" in decision.error_message


def test_startup_recovery_requeues_pending_when_payload_is_valid() -> None:
    decision = decide_startup_recovery(
        LoadJobState.PENDING,
        payload_file_exists=True,
        checksum_matches=True,
    )

    assert decision.state is LoadJobState.PENDING
    assert decision.should_enqueue is True
    assert decision.error_message is None


def test_startup_recovery_fails_pending_when_payload_is_missing() -> None:
    decision = decide_startup_recovery(
        LoadJobState.PENDING,
        payload_file_exists=False,
        checksum_matches=True,
    )

    assert decision.state is LoadJobState.FAILED
    assert decision.should_enqueue is False
    assert decision.error_message is not None
    assert "payload" in decision.error_message


def test_startup_recovery_fails_pending_when_checksum_mismatches() -> None:
    decision = decide_startup_recovery(
        LoadJobState.PENDING,
        payload_file_exists=True,
        checksum_matches=False,
    )

    assert decision.state is LoadJobState.FAILED
    assert decision.should_enqueue is False


def test_startup_recovery_leaves_terminal_states_unqueued() -> None:
    for state in (LoadJobState.SUCCESS, LoadJobState.FAILED, LoadJobState.CANCELLED):
        decision = decide_startup_recovery(state)

        assert decision.state is state
        assert decision.should_enqueue is False
        assert decision.error_message is None
