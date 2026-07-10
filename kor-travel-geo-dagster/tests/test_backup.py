"""Scheduled-backup Dagster onramp tests (T-290f)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from dagster import Failure, build_op_context, build_schedule_context
from kortravelgeo.settings import Settings
from pydantic import SecretStr

from kortravelgeo_dagster.backup import (
    JOB_ID_TAG,
    JOB_KIND_TAG,
    _dict_value,
    _dispatch_run_failure_notification,
    _failure_notification_payload,
    _nested_value,
    _run_due_metadata,
    _scheduled_backup_run_request,
    run_due_scheduled_backup_op,
    scheduled_backup_schedule,
)
from kortravelgeo_dagster.resources import (
    ACTOR_HEADER,
    ADMIN_PROXY_SECRET_HEADER,
    DESTRUCTIVE_ADMIN_ROLE,
    ROLES_HEADER,
    SCHEDULER_ROLE,
    SYSTEM_ACTOR,
    DagsterAdminApiClient,
)


class _FakeError:
    def __init__(self, cls_name: object) -> None:
        self.cls_name = cls_name


class _FakeEventData:
    def __init__(self, error: object) -> None:
        self.error = error


class _FakeFailureEvent:
    def __init__(self, error_cls_name: object, message: str) -> None:
        self.event_specific_data = _FakeEventData(_FakeError(error_cls_name))
        self.message = message


class _FakeDagsterRun:
    def __init__(
        self, run_id: str, job_name: str | None, status: str, tags: dict[str, str]
    ) -> None:
        self.run_id = run_id
        self.job_name = job_name
        self.status = status
        self.tags = tags


class _FakeFailureContext:
    def __init__(self, dagster_run: _FakeDagsterRun, failure_event: object) -> None:
        self.dagster_run = dagster_run
        self.failure_event = failure_event


def test_failure_notification_payload_matches_boundary_contract() -> None:
    context = _FakeFailureContext(
        dagster_run=_FakeDagsterRun(
            run_id="run-9",
            job_name="mv_refresh_job",
            status="DagsterRunStatus.FAILURE",
            tags={JOB_ID_TAG: "job-42"},
        ),
        failure_event=_FakeFailureEvent(
            error_cls_name="Failure",
            message="secret internal traceback detail",
        ),
    )

    payload = _failure_notification_payload(context)  # type: ignore[arg-type]

    assert payload == {
        "job_id": "job-42",
        "run_id": "run-9",
        "job_name": "mv_refresh_job",
        "status": "DagsterRunStatus.FAILURE",
        "error_code": "Failure",
    }
    # The raw Dagster failure message must never reach the notifier.
    assert "message" not in payload
    assert "secret internal traceback detail" not in payload.values()


def test_failure_notification_payload_defaults_when_unavailable() -> None:
    context = _FakeFailureContext(
        dagster_run=_FakeDagsterRun(
            run_id="run-x",
            job_name=None,
            status="DagsterRunStatus.FAILURE",
            tags={},
        ),
        failure_event=None,
    )

    payload = _failure_notification_payload(context)  # type: ignore[arg-type]

    assert payload["run_id"] == "run-x"
    assert payload["job_id"] is None
    assert payload["error_code"] is None
    assert "message" not in payload


def test_admin_api_client_uses_settings_and_proxy_headers() -> None:
    client = DagsterAdminApiClient.from_settings(
        Settings(
            _env_file=None,
            dagster_admin_api_url="http://geo-api.internal:12501/",
            admin_proxy_secret=SecretStr("shared-secret"),
        )
    )

    assert client.base_url == "http://geo-api.internal:12501"
    assert client.url_for("/v1/admin/backups/scheduled/run-due") == (
        "http://geo-api.internal:12501/v1/admin/backups/scheduled/run-due"
    )
    # #429 least privilege: the scheduled-backup on-ramp presents `scheduler`, not
    # `destructive_admin`. run-due is gated to scheduler/destructive_admin server-side.
    assert client.roles == (SCHEDULER_ROLE,)
    assert client.headers() == {
        ACTOR_HEADER: SYSTEM_ACTOR,
        ROLES_HEADER: SCHEDULER_ROLE,
        ADMIN_PROXY_SECRET_HEADER: "shared-secret",
    }


@pytest.mark.asyncio
async def test_admin_api_client_posts_run_due() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "enqueued": True,
                "job_id": "job-1",
                "status": {"due": True, "reason": "due_initial"},
            },
        )

    client = DagsterAdminApiClient(
        base_url="http://geo-api.internal:12501",
        timeout_seconds=1.0,
        admin_proxy_secret="shared-secret",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        payload = await client.run_due_scheduled_backup(http_client=http_client)

    assert payload["enqueued"] is True
    assert requests[0].url == "http://geo-api.internal:12501/v1/admin/backups/scheduled/run-due"
    assert requests[0].headers[ACTOR_HEADER] == SYSTEM_ACTOR
    assert requests[0].headers[ROLES_HEADER] == SCHEDULER_ROLE
    assert requests[0].headers[ADMIN_PROXY_SECRET_HEADER] == "shared-secret"


def test_admin_api_client_defaults_to_least_privilege_scheduler_role() -> None:
    # Default construction (from_settings) presents only the least-privilege scheduler
    # role — never destructive_admin (#429 / ADR-066).
    client = DagsterAdminApiClient.from_settings(
        Settings(_env_file=None, dagster_admin_api_url="http://geo-api.internal:12501/")
    )
    assert client.roles == (SCHEDULER_ROLE,)
    assert client.headers()[ROLES_HEADER] == SCHEDULER_ROLE
    assert DESTRUCTIVE_ADMIN_ROLE not in client.headers()[ROLES_HEADER]


def test_admin_api_client_allows_explicit_destructive_override() -> None:
    # A future destructive on-ramp (e.g. restore) may opt in explicitly; the client
    # does not hardcode scheduler, it only defaults to it.
    client = DagsterAdminApiClient(
        base_url="http://geo-api.internal:12501",
        timeout_seconds=1.0,
        roles=(DESTRUCTIVE_ADMIN_ROLE,),
    )
    assert client.headers()[ROLES_HEADER] == DESTRUCTIVE_ADMIN_ROLE


# --- op body: run_due_scheduled_backup_op (#431) -----------------------------------


class _FakeAdminApi:
    """Stand-in for DagsterAdminApiClient — records the call, returns a canned body."""

    def __init__(
        self, *, payload: dict[str, object] | None = None, error: Exception | None = None
    ) -> None:
        self._payload = payload if payload is not None else {}
        self._error = error
        self.calls = 0

    async def run_due_scheduled_backup(self, *, http_client: object = None) -> dict[str, object]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._payload


@pytest.mark.asyncio
async def test_run_due_op_enqueued_branch() -> None:
    fake = _FakeAdminApi(
        payload={
            "enqueued": True,
            "job_id": "job-1",
            "status": {
                "due": True,
                "reason": "due_initial",
                "next_due_at": "2026-01-01T00:00:00Z",
            },
        }
    )
    with build_op_context(resources={"admin_api": fake}) as ctx:
        result = await run_due_scheduled_backup_op(ctx)
    assert result["enqueued"] is True
    assert result["job_id"] == "job-1"
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_run_due_op_not_enqueued_branch() -> None:
    fake = _FakeAdminApi(
        payload={"enqueued": False, "status": {"due": False, "reason": "interval_not_elapsed"}}
    )
    with build_op_context(resources={"admin_api": fake}) as ctx:
        result = await run_due_scheduled_backup_op(ctx)
    assert result["enqueued"] is False
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_run_due_op_wraps_api_error_as_failure() -> None:
    fake = _FakeAdminApi(error=RuntimeError("boom"))
    with build_op_context(resources={"admin_api": fake}) as ctx, pytest.raises(Failure):
        await run_due_scheduled_backup_op(ctx)


# --- schedule: scheduled_backup_schedule (run_key / RunRequest tags) ----------------


def test_schedule_run_request_uses_scheduled_time_as_run_key() -> None:
    dt = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    with build_schedule_context(scheduled_execution_time=dt) as sctx:
        req = scheduled_backup_schedule(sctx)
    assert req.run_key == dt.isoformat()
    assert req.tags["kor_travel_geo.schedule"] == "scheduled_backup"
    assert req.tags["kor_travel_geo.job_kind"] == "scheduled_backup_run_due"


def test_schedule_run_request_none_run_key_without_scheduled_time() -> None:
    # Defensive fallback: with no scheduled_execution_time the run_key is None. Tested via
    # the extracted helper — direct @schedule invocation type-checks the context.
    req = _scheduled_backup_run_request(None)
    assert req.run_key is None
    assert req.tags["kor_travel_geo.schedule"] == "scheduled_backup"


# --- run-due metadata helpers (_run_due_metadata / _nested_value / _dict_value) -----


def test_dict_value_handles_non_dict_and_missing_keys() -> None:
    assert _dict_value({"a": 1}, "a") == 1
    assert _dict_value({"a": 1}, "b") is None
    assert _dict_value(None, "a") is None
    assert _dict_value("not-a-dict", "a") is None


def test_nested_value_reads_two_levels_defensively() -> None:
    assert _nested_value({"status": {"reason": "x"}}, "status", "reason") == "x"
    assert _nested_value({"status": None}, "status", "reason") is None
    assert _nested_value({}, "status", "reason") is None


def test_run_due_metadata_flattens_status_fields() -> None:
    payload = {
        "enqueued": True,
        "job_id": "j1",
        "skipped_locked": False,
        "status": {"due": True, "reason": "due_initial", "next_due_at": "2026-01-01T00:00:00Z"},
    }
    assert _run_due_metadata(payload) == {
        "enqueued": True,
        "job_id": "j1",
        "skipped_locked": False,
        "due": True,
        "reason": "due_initial",
        "next_due_at": "2026-01-01T00:00:00Z",
    }


def test_run_due_metadata_defaults_when_status_absent() -> None:
    md = _run_due_metadata({"enqueued": False})
    assert md["enqueued"] is False
    assert md["skipped_locked"] is False
    assert md["due"] is None
    assert md["reason"] is None
    assert md["next_due_at"] is None


# --- failure-sensor dispatch: _dispatch_run_failure_notification --------------------


class _RecordingLog:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args: object) -> None:
        self.warnings.append(msg % args if args else msg)


class _FakeClient:
    """Duck-typed ``AsyncAddressClient`` recording ``record_run_failure_alert`` calls."""

    def __init__(self, *, raises: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self._raises = raises

    async def record_run_failure_alert(self, **kwargs: object) -> dict[str, object]:
        if self._raises:
            raise RuntimeError("db unavailable")
        self.calls.append(kwargs)
        return kwargs


def _failure_context() -> _FakeFailureContext:
    ctx = _FakeFailureContext(
        dagster_run=_FakeDagsterRun(
            run_id="run-1",
            job_name="scheduled_backup_run_due",
            status="DagsterRunStatus.FAILURE",
            tags={JOB_ID_TAG: "job-7", JOB_KIND_TAG: "scheduled_backup_run_due"},
        ),
        failure_event=_FakeFailureEvent(error_cls_name="Failure", message="internal detail"),
    )
    ctx.log = _RecordingLog()  # type: ignore[attr-defined]
    return ctx


def _dispatch(
    ctx: _FakeFailureContext, *, client: object = None, failure_notifier: object = None
) -> None:
    """Invoke the dispatch helper with resources injected explicitly (as the sensor does)."""
    _dispatch_run_failure_notification(
        ctx,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        failure_notifier=failure_notifier,
    )


def test_dispatch_forwards_boundary_payload_to_callable_notifier() -> None:
    received: list[dict[str, object]] = []
    _dispatch(_failure_context(), failure_notifier=received.append)
    assert len(received) == 1
    assert received[0]["run_id"] == "run-1"
    assert received[0]["job_id"] == "job-7"
    assert received[0]["error_code"] == "Failure"
    # §5: the raw Dagster failure message must never reach the notifier.
    assert "message" not in received[0]
    assert "internal detail" not in received[0].values()


def test_dispatch_without_notifier_warns_and_returns() -> None:
    ctx = _failure_context()
    _dispatch(ctx, failure_notifier=None)  # must not raise
    assert ctx.log.warnings  # type: ignore[attr-defined]


def test_dispatch_with_non_callable_notifier_warns_and_returns() -> None:
    ctx = _failure_context()
    _dispatch(ctx, failure_notifier=object())  # non-callable resource; must not raise
    assert ctx.log.warnings  # type: ignore[attr-defined]


def test_dispatch_persists_bounded_alert_via_client() -> None:
    client = _FakeClient()
    _dispatch(_failure_context(), client=client)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["run_id"] == "run-1"
    assert call["job_id"] == "job-7"
    assert call["job_name"] == "scheduled_backup_run_due"
    assert call["job_kind"] == "scheduled_backup_run_due"
    assert call["error_code"] == "Failure"
    # status is normalized to the bare run-status name (matches the observe GraphQL).
    assert call["status"] == "FAILURE"
    assert isinstance(call["run_failed_at"], datetime)
    # §5: the raw Dagster failure message must never be persisted.
    assert "message" not in call
    assert "internal detail" not in call.values()


def test_dispatch_without_client_warns_and_skips_persist() -> None:
    ctx = _failure_context()
    _dispatch(ctx, client=None)  # must not raise
    assert ctx.log.warnings  # type: ignore[attr-defined]


def test_dispatch_persist_failure_is_swallowed() -> None:
    ctx = _failure_context()
    _dispatch(ctx, client=_FakeClient(raises=True))  # persistence error must not raise
    assert ctx.log.warnings  # type: ignore[attr-defined]


def test_dispatch_persist_and_notify_run_independently() -> None:
    received: list[dict[str, object]] = []
    client = _FakeClient()
    _dispatch(_failure_context(), client=client, failure_notifier=received.append)
    assert len(client.calls) == 1  # persisted
    assert len(received) == 1  # and notified
