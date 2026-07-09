"""run_backup_job / run_restore_job strip internal _job_id before strict DTO validation.

Regression (T-290g): the JobQueue drain and the Dagster db_backup op inject `_job_id` into
the job payload to link the run to its load_jobs row, but BackupCreateRequest /
RestoreCreateRequest forbid extra fields. The leaf must drop `_`-prefixed control keys
before model_validate while still reading `_job_id` from the full payload.
"""

from __future__ import annotations

from kortravelgeo.dto.admin import BackupCreateRequest, RestoreCreateRequest
from kortravelgeo.infra.backup import _payload_job_id, _request_payload


def test_request_payload_drops_underscore_control_keys() -> None:
    payload = {"display_name": "e2e", "_job_id": "job-1", "_extra": 5}
    cleaned = _request_payload(payload)
    assert cleaned == {"display_name": "e2e"}
    # the full payload still yields the job id for run linkage
    assert _payload_job_id(payload) == "job-1"


def test_backup_request_validates_after_stripping_job_id() -> None:
    # A payload carrying the injected _job_id must validate once stripped (it would raise
    # extra_forbidden otherwise — the bug the Dagster db_backup run first exposed).
    payload = {"display_name": "e2e", "_job_id": "job-abc"}
    req = BackupCreateRequest.model_validate(_request_payload(payload))
    assert req.display_name == "e2e"


def test_restore_request_validates_after_stripping_job_id() -> None:
    payload = {"artifact_id": "art-1", "mode": "new_database", "_job_id": "job-xyz"}
    req = RestoreCreateRequest.model_validate(_request_payload(payload))
    assert req.artifact_id == "art-1"
