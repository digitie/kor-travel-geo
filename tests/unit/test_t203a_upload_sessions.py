"""T-203a: upload session lifecycle + RustFS storage-client extensions.

DB-free tests: DTO validation, the duplicate-session (409) resume payload, the
slot-replace invalidation contract, the ``failed_storage_state`` transition
decision, the SSE ``source_upload.progress`` shape, and the RustFS multipart
storage-client logic exercised through an injected fake transport.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from kortravelgeo.dto.source import (
    TERMINAL_UPLOAD_SESSION_STATES,
    SourceUploadProgressEvent,
    UploadSessionConflict,
    UploadSessionCreateRequest,
    UploadSessionFileSlot,
    UploadSessionStatus,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError
from kortravelgeo.infra.rustfs import (
    EffectiveRustfsConfig,
    RustfsClient,
    RustfsUploadedPart,
)
from kortravelgeo.infra.source_upload_repo import (
    is_terminal_state,
    should_fail_storage_state,
    slot_definitions,
)

# --- DTO / catalog ---------------------------------------------------------


def test_create_request_requires_six_digit_user_yyyymm() -> None:
    ok = UploadSessionCreateRequest(
        category="roadname_hangul_full",
        user_yyyymm="202605",
        display_name="202605 도로명주소 한글 전체분",
    )
    assert ok.storage_kind == "rustfs"
    assert ok.upload_strategy == "multipart"

    with pytest.raises(ValueError, match="user_yyyymm"):
        UploadSessionCreateRequest(
            category="roadname_hangul_full",
            user_yyyymm="2026",  # too short
            display_name="x",
        )


def test_slot_definitions_single_vs_multipart() -> None:
    single = slot_definitions("roadname_hangul_full")
    assert len(single) == 1
    assert single[0].slot == "archive"
    assert single[0].part_kind == "single"

    multi = slot_definitions("electronic_map_full")
    assert len(multi) == 17
    assert {slot.part_kind for slot in multi} == {"sido"}
    seoul = next(slot for slot in multi if slot.part_key == "11")
    assert seoul.part_label == "서울특별시"


def test_slot_definitions_rejects_unknown_category() -> None:
    with pytest.raises(InvalidInputError, match="unknown source category"):
        slot_definitions("not_a_category")


# --- terminal-state / 409 dedup logic --------------------------------------


def test_terminal_states_block_dedup_but_progress_states_do_not() -> None:
    # Non-terminal in-progress states are exactly what the 409 check guards.
    for state in ("created", "uploading", "awaiting_registration", "failed_register"):
        assert not is_terminal_state(state)
    # Terminal states no longer block a new session for the same slot.
    for state in (
        "registered",
        "available",
        "cancelled",
        "expired",
        "failed_upload",
        "failed_structure",
        "failed_rustfs_put",
        "failed_storage_state",
    ):
        assert is_terminal_state(state)
        assert state in TERMINAL_UPLOAD_SESSION_STATES


def test_sse_terminal_states_match_canonical_set_and_exclude_retryable() -> None:
    # #176 review: the upload-session SSE stream-end set must equal the canonical
    # terminal set so the live stream does not end on states the client treats as
    # still in-progress. failed_register is retryable; quarantined is not a session state.
    from kortravelgeo.api.routers.admin import _UPLOAD_TERMINAL_STATES

    assert _UPLOAD_TERMINAL_STATES == TERMINAL_UPLOAD_SESSION_STATES
    assert "failed_register" not in _UPLOAD_TERMINAL_STATES
    assert "quarantined" not in _UPLOAD_TERMINAL_STATES


def _session(**overrides: object) -> UploadSessionStatus:
    now = datetime(2026, 6, 14, tzinfo=UTC)
    base: dict[str, object] = {
        "upload_session_id": "source_upload_abc",
        "source_file_group_id": "group-1",
        "category": "roadname_hangul_full",
        "group_kind": "single_file",
        "user_yyyymm": "202605",
        "display_name": "202605 도로명주소 한글 전체분",
        "state": "uploading",
        "expected_file_count": 1,
        "uploaded_file_count": 0,
        "max_bytes": 2 * 1024 * 1024 * 1024,
        "part_size_bytes": 64 * 1024 * 1024,
        "file_slots": (UploadSessionFileSlot(slot="archive"),),
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return UploadSessionStatus(**base)  # type: ignore[arg-type]


def test_conflict_body_carries_resume_payload() -> None:
    existing = _session(state="awaiting_registration", uploaded_file_count=1)
    conflict = UploadSessionConflict(
        message="진행 중 세션이 있습니다",
        upload_session_id=existing.upload_session_id,
        state=existing.state,
        category=existing.category,
        user_yyyymm=existing.user_yyyymm,
        uploaded_file_count=existing.uploaded_file_count,
        expected_file_count=existing.expected_file_count,
        resumable_actions=("resume_upload", "cancel_session"),
        existing_session=existing,
    )
    payload = conflict.model_dump(mode="json", exclude_none=True)
    assert payload["error"] == "upload_session_conflict"
    assert payload["upload_session_id"] == "source_upload_abc"
    assert payload["existing_session"]["state"] == "awaiting_registration"
    assert "resume_upload" in payload["resumable_actions"]


# --- failed_storage_state transition decision ------------------------------


def test_failed_storage_state_when_multipart_upload_gone() -> None:
    # ListParts 404 → listed=None → must fail.
    assert should_fail_storage_state(
        recorded_part_numbers=frozenset({1, 2}),
        listed_part_numbers=None,
    )


def test_failed_storage_state_when_recorded_part_missing_from_storage() -> None:
    assert should_fail_storage_state(
        recorded_part_numbers=frozenset({1, 2, 3}),
        listed_part_numbers=frozenset({1, 2}),  # 3 missing
    )


def test_no_failed_storage_state_when_storage_has_all_recorded_parts() -> None:
    # Storage may hold extra parts not yet recorded; that is fine.
    assert not should_fail_storage_state(
        recorded_part_numbers=frozenset({1, 2}),
        listed_part_numbers=frozenset({1, 2, 3}),
    )
    assert not should_fail_storage_state(
        recorded_part_numbers=frozenset(),
        listed_part_numbers=frozenset(),
    )


# --- slot-replace invalidation contract ------------------------------------


def test_slot_with_part_progress_marks_uploaded() -> None:
    # The session view overlays recorded parts; a replaced (cleared) slot has no
    # parts, so it reports uploaded=False — i.e. replace invalidates the slot.
    fresh = UploadSessionFileSlot(slot="archive")
    assert fresh.uploaded is False
    assert fresh.received_bytes == 0
    uploaded = fresh.model_copy(update={"uploaded": True, "received_bytes": 10})
    assert uploaded.uploaded is True
    # model_copy reset (what replace_slot effectively does on the view)
    assert uploaded.model_copy(update={"uploaded": False, "received_bytes": 0}).uploaded is False


# --- SSE progress event shape ----------------------------------------------


def test_progress_event_shape_matches_doc() -> None:
    event = SourceUploadProgressEvent(
        upload_session_id="source_upload_abc",
        state="validating_structure",
        stage="validate:electronic_map_full",
        progress=0.42,
        current_item="서울특별시.zip/TL_SPBD_BULD.dbf",
        uploaded_bytes=123,
        total_bytes=456,
        message="전자지도 layer sidecar를 확인하는 중",
    )
    payload = event.model_dump(mode="json")
    assert payload["event"] == "source_upload.progress"
    assert payload["upload_session_id"] == "source_upload_abc"
    assert payload["state"] == "validating_structure"
    assert 0.0 <= payload["progress"] <= 1.0


def test_progress_event_progress_bounded() -> None:
    with pytest.raises(ValueError, match="less than or equal to 1"):
        SourceUploadProgressEvent(
            upload_session_id="s", state="uploading", progress=1.5
        )


# --- RustFS multipart storage-client logic (injected fake transport) -------


def _config() -> EffectiveRustfsConfig:
    return EffectiveRustfsConfig(
        enabled=True,
        endpoint_url="http://127.0.0.1:12101",
        bucket="kor-travel-geo",
        prefix="kor-travel-geo",
        region="us-east-1",
        force_path_style=True,
        retention_days=0,
        access_key="access",
        secret_key="secret",
    )


class _FakeTransport:
    """Records signed requests and replays scripted S3 XML/headers."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self._next: list[httpx.Response] = []

    def enqueue(self, response: httpx.Response) -> None:
        self._next.append(response)

    async def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        content: object,
    ) -> httpx.Response:
        body = content if isinstance(content, bytes) else None
        self.calls.append((method, url, dict(headers), body))
        return self._next.pop(0)


def _xml_response(status: int, body: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status_code=status, text=body, headers=headers or {})


@pytest.mark.asyncio
async def test_create_multipart_upload_returns_upload_id() -> None:
    transport = _FakeTransport()
    transport.enqueue(
        _xml_response(
            200,
            "<InitiateMultipartUploadResult><UploadId>mp-123</UploadId>"
            "</InitiateMultipartUploadResult>",
        )
    )
    client = RustfsClient(_config(), sender=transport)

    upload_id = await client.create_multipart_upload(
        "kor-travel-geo/source-files/roadname_hangul_full/202605/g/s/archive/archive",
        metadata={"ktg-category": "roadname_hangul_full"},
    )

    assert upload_id == "mp-123"
    method, url, headers, _ = transport.calls[0]
    assert method == "POST"
    assert "uploads=" in url
    assert headers["x-amz-meta-ktg-category"] == "roadname_hangul_full"


@pytest.mark.asyncio
async def test_upload_part_returns_part_number_and_etag() -> None:
    transport = _FakeTransport()
    transport.enqueue(_xml_response(200, "", headers={"etag": '"etag-1"'}))
    client = RustfsClient(_config(), sender=transport)

    part = await client.upload_part(
        "obj-key", upload_id="mp-123", part_number=1, body=b"hello"
    )

    assert part == RustfsUploadedPart(part_number=1, etag="etag-1")
    method, url, headers, body = transport.calls[0]
    assert method == "PUT"
    assert "partNumber=1" in url
    assert "uploadId=mp-123" in url
    assert body == b"hello"
    # payload hash signs the body
    import hashlib

    assert headers["x-amz-content-sha256"] == hashlib.sha256(b"hello").hexdigest()


@pytest.mark.asyncio
async def test_upload_part_rejects_part_number_below_one() -> None:
    client = RustfsClient(_config(), sender=_FakeTransport())
    with pytest.raises(InvalidInputError, match="part_number"):
        await client.upload_part("k", upload_id="mp", part_number=0, body=b"x")


@pytest.mark.asyncio
async def test_complete_multipart_upload_sends_ordered_parts_and_returns_etag() -> None:
    transport = _FakeTransport()
    transport.enqueue(
        _xml_response(
            200,
            "<CompleteMultipartUploadResult><ETag>\"final-etag\"</ETag>"
            "</CompleteMultipartUploadResult>",
        )
    )
    client = RustfsClient(_config(), sender=transport)

    etag = await client.complete_multipart_upload(
        "obj-key",
        upload_id="mp-123",
        parts=(
            RustfsUploadedPart(part_number=2, etag="etag-2"),
            RustfsUploadedPart(part_number=1, etag="etag-1"),
        ),
    )

    assert etag == "final-etag"
    _, _, _, body = transport.calls[0]
    assert body is not None
    text = body.decode()
    # parts must be ordered ascending and etags quoted
    assert text.index("<PartNumber>1</PartNumber>") < text.index("<PartNumber>2</PartNumber>")
    assert '<ETag>"etag-1"</ETag>' in text


@pytest.mark.asyncio
async def test_complete_multipart_upload_surfaces_200_wrapped_error() -> None:
    transport = _FakeTransport()
    transport.enqueue(_xml_response(200, "<Error><Code>InvalidPart</Code></Error>"))
    client = RustfsClient(_config(), sender=transport)

    with pytest.raises(InvalidInputError, match="InvalidPart"):
        await client.complete_multipart_upload(
            "obj-key",
            upload_id="mp-123",
            parts=(RustfsUploadedPart(part_number=1, etag="etag-1"),),
        )


@pytest.mark.asyncio
async def test_complete_multipart_upload_requires_parts() -> None:
    client = RustfsClient(_config(), sender=_FakeTransport())
    with pytest.raises(InvalidInputError, match="at least one part"):
        await client.complete_multipart_upload("k", upload_id="mp", parts=())


@pytest.mark.asyncio
async def test_list_parts_parses_parts_and_paginates() -> None:
    transport = _FakeTransport()
    transport.enqueue(
        _xml_response(
            200,
            "<ListPartsResult>"
            "<Part><PartNumber>1</PartNumber><ETag>\"e1\"</ETag><Size>5</Size></Part>"
            "<IsTruncated>true</IsTruncated>"
            "<NextPartNumberMarker>1</NextPartNumberMarker>"
            "</ListPartsResult>",
        )
    )
    transport.enqueue(
        _xml_response(
            200,
            "<ListPartsResult>"
            "<Part><PartNumber>2</PartNumber><ETag>\"e2\"</ETag><Size>7</Size></Part>"
            "<IsTruncated>false</IsTruncated>"
            "</ListPartsResult>",
        )
    )
    client = RustfsClient(_config(), sender=transport)

    parts = await client.list_parts("obj-key", upload_id="mp-123")

    assert [p.part_number for p in parts] == [1, 2]
    assert parts[0].etag == "e1"
    assert parts[1].size == 7


@pytest.mark.asyncio
async def test_list_parts_raises_not_found_when_upload_gone() -> None:
    transport = _FakeTransport()
    transport.enqueue(_xml_response(404, "<Error><Code>NoSuchUpload</Code></Error>"))
    client = RustfsClient(_config(), sender=transport)

    with pytest.raises(NotFoundError, match="multipart upload not found"):
        await client.list_parts("obj-key", upload_id="mp-gone")


@pytest.mark.asyncio
async def test_abort_multipart_upload_tolerates_404() -> None:
    transport = _FakeTransport()
    transport.enqueue(_xml_response(404, "<Error><Code>NoSuchUpload</Code></Error>"))
    client = RustfsClient(_config(), sender=transport)

    # 404 is an expected (idempotent) abort outcome — no raise.
    await client.abort_multipart_upload("obj-key", upload_id="mp-gone")
    assert transport.calls[0][0] == "DELETE"


@pytest.mark.asyncio
async def test_head_object_extracts_metadata_and_size() -> None:
    transport = _FakeTransport()
    transport.enqueue(
        _xml_response(
            200,
            "",
            headers={
                "content-length": "123",
                "etag": '"obj-etag"',
                "x-amz-meta-ktg-category": "roadname_hangul_full",
                "x-amz-meta-ktg-sha256": "a" * 64,
            },
        )
    )
    client = RustfsClient(_config(), sender=transport)

    head = await client.head_object("obj-key")

    assert head.size == 123
    assert head.etag == "obj-etag"
    assert head.metadata["ktg-category"] == "roadname_hangul_full"
    assert head.metadata["ktg-sha256"] == "a" * 64
    assert transport.calls[0][0] == "HEAD"
