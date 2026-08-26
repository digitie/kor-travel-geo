"""T-291c contract tests: POST /v2/dataset/version, POST /v2/dataset/history.

The repository layer (AdminRepository's dataset-version methods) is monkeypatched with a
fake — these tests exercise routing, request validation, response shape, and the
changed/known_version_found/since_found decision logic, not the SQL projection itself (that
needs a real DB; see the live-DB integration test)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.api.routers import dataset as dataset_router
from kortravelgeo.dto.v2 import DatasetVersionEntry


class _FakeClient:
    def _engine(self) -> object:
        return object()


class _FakeRepo:
    """Stands in for AdminRepository — the router only calls these 3 methods."""

    current: DatasetVersionEntry | None = None
    by_token: ClassVar[dict[str, DatasetVersionEntry]] = {}
    history_page: ClassVar[list[DatasetVersionEntry]] = []
    history_has_more: bool = False

    def __init__(self, _engine: object) -> None:
        pass

    async def current_dataset_version(self) -> DatasetVersionEntry | None:
        return _FakeRepo.current

    async def find_dataset_version(self, version_token: str) -> DatasetVersionEntry | None:
        return _FakeRepo.by_token.get(version_token)

    async def dataset_version_history(
        self, *, limit: int, before: Any = None, since: Any = None
    ) -> tuple[list[DatasetVersionEntry], bool]:
        return _FakeRepo.history_page, _FakeRepo.history_has_more


def _entry(
    token: str,
    *,
    activated_at: datetime | None = None,
    change_type: str = "full",
    reference_months: dict[str, str] | None = None,
) -> DatasetVersionEntry:
    return DatasetVersionEntry(
        version_token=token,
        activated_at=activated_at or datetime(2026, 8, 20, 3, 12, 45, tzinfo=UTC),
        change_type=change_type,  # type: ignore[arg-type]
        reference_months=reference_months,
        reference_months_mixed=False,
    )


@pytest.fixture(autouse=True)
def _reset_fake_repo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dataset_router, "AdminRepository", _FakeRepo)
    _FakeRepo.current = None
    _FakeRepo.by_token = {}
    _FakeRepo.history_page = []
    _FakeRepo.history_has_more = False
    yield


async def _post(app: Any, path: str, json: dict[str, Any] | None = None) -> httpx.Response:
    app.dependency_overrides[get_client] = lambda: _FakeClient()
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=json or {})


@pytest.mark.asyncio
async def test_version_reports_unavailable_when_no_active_release() -> None:
    app = create_app()
    response = await _post(app, "/v2/dataset/version")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "current" not in body
    assert "changed" not in body
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_version_omits_known_version_fields_when_not_asked() -> None:
    app = create_app()
    token = "dv1-" + "a" * 32
    _FakeRepo.current = _entry(token)
    response = await _post(app, "/v2/dataset/version")
    body = response.json()
    assert body["available"] is True
    assert body["current"]["version_token"] == token
    assert "changed" not in body
    assert "known_version_found" not in body


@pytest.mark.asyncio
async def test_version_known_version_matches_current_reports_unchanged() -> None:
    app = create_app()
    token = "dv1-" + "a" * 32
    _FakeRepo.current = _entry(token)
    response = await _post(app, "/v2/dataset/version", {"known_version": token})
    body = response.json()
    assert body["changed"] is False
    assert body["known_version_found"] is True
    assert body["current"]["version_token"] == token


@pytest.mark.asyncio
async def test_version_known_version_stale_but_found_in_history() -> None:
    app = create_app()
    current_token = "dv1-" + "b" * 32
    old_token = "dv1-" + "c" * 32
    _FakeRepo.current = _entry(current_token)
    _FakeRepo.by_token = {old_token: _entry(old_token)}
    response = await _post(app, "/v2/dataset/version", {"known_version": old_token})
    body = response.json()
    assert body["changed"] is True
    assert body["known_version_found"] is True


@pytest.mark.asyncio
async def test_version_known_version_not_found_signals_history_reset() -> None:
    """A restore/history-reset scenario: the caller's stored token no longer appears
    anywhere in the ledger — known_version_found:false means "resync everything"."""
    app = create_app()
    current_token = "dv1-" + "d" * 32
    vanished_token = "dv1-" + "e" * 32
    _FakeRepo.current = _entry(current_token)
    _FakeRepo.by_token = {}
    response = await _post(app, "/v2/dataset/version", {"known_version": vanished_token})
    body = response.json()
    assert body["changed"] is True
    assert body["known_version_found"] is False


@pytest.mark.asyncio
async def test_version_rejects_malformed_known_version_format() -> None:
    app = create_app()
    response = await _post(app, "/v2/dataset/version", {"known_version": "not-a-token"})
    assert response.status_code == 400
    assert response.json()["status"] == "ERROR"


@pytest.mark.asyncio
async def test_version_response_never_exposes_internal_fields() -> None:
    """Public-scope regression guard (ADR-067 D2 non-goals) — even if a future change makes
    the repository/DTO layer carry extra attributes, response_model_exclude_none + the
    FrozenModel(extra="forbid") DTO must keep them off the wire."""
    app = create_app()
    token = "dv1-" + "f" * 32
    _FakeRepo.current = _entry(token)
    response = await _post(app, "/v2/dataset/version")
    body = response.json()
    forbidden = {
        "serving_release_id",
        "dataset_snapshot_id",
        "mv_hash",
        "source_set",
        "source_set_hash",
        "row_counts",
        "state",
    }
    assert forbidden.isdisjoint(body)
    assert forbidden.isdisjoint(body.get("current", {}))


@pytest.mark.asyncio
async def test_history_reports_since_found_and_entries() -> None:
    app = create_app()
    anchor_token = "dv1-" + "0" * 32
    _FakeRepo.by_token = {anchor_token: _entry(anchor_token)}
    _FakeRepo.history_page = [_entry("dv1-" + "1" * 32)]
    _FakeRepo.history_has_more = False
    response = await _post(app, "/v2/dataset/history", {"since_version": anchor_token})
    body = response.json()
    assert body["since_found"] is True
    assert len(body["entries"]) == 1
    assert "next_cursor" not in body


@pytest.mark.asyncio
async def test_history_since_version_not_found_still_returns_newest_page() -> None:
    """History-reset contract (design doc §1.2): an unresolvable since_version falls through
    to the newest page rather than erroring — the consumer's own since_found:false handling
    is "resync everything," and an empty/error response would defeat that."""
    app = create_app()
    _FakeRepo.by_token = {}
    _FakeRepo.history_page = [_entry("dv1-" + "2" * 32)]
    response = await _post(app, "/v2/dataset/history", {"since_version": "dv1-" + "9" * 32})
    body = response.json()
    assert body["since_found"] is False
    assert len(body["entries"]) == 1


@pytest.mark.asyncio
async def test_history_omits_since_found_when_since_version_not_given() -> None:
    app = create_app()
    _FakeRepo.history_page = [_entry("dv1-" + "3" * 32)]
    response = await _post(app, "/v2/dataset/history")
    assert "since_found" not in response.json()


@pytest.mark.asyncio
async def test_history_emits_next_cursor_when_more_pages_remain() -> None:
    app = create_app()
    _FakeRepo.history_page = [_entry("dv1-" + "4" * 32)]
    _FakeRepo.history_has_more = True
    response = await _post(app, "/v2/dataset/history")
    assert response.json()["next_cursor"] is not None


@pytest.mark.asyncio
async def test_history_omits_next_cursor_on_the_last_page() -> None:
    app = create_app()
    _FakeRepo.history_page = [_entry("dv1-" + "5" * 32)]
    _FakeRepo.history_has_more = False
    response = await _post(app, "/v2/dataset/history")
    assert "next_cursor" not in response.json()


@pytest.mark.asyncio
async def test_history_rejects_unparseable_cursor() -> None:
    app = create_app()
    response = await _post(app, "/v2/dataset/history", {"cursor": "not valid base64!!"})
    assert response.status_code == 400
    assert response.json()["status"] == "ERROR"


@pytest.mark.asyncio
async def test_history_rejects_limit_out_of_range() -> None:
    app = create_app()
    response = await _post(app, "/v2/dataset/history", {"limit": 101})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_both_endpoints_set_cache_control_no_store() -> None:
    app = create_app()
    version_response = await _post(app, "/v2/dataset/version")
    history_response = await _post(app, "/v2/dataset/history")
    assert version_response.headers["Cache-Control"] == "no-store"
    assert history_response.headers["Cache-Control"] == "no-store"
