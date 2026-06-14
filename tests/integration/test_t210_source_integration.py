"""T-210 source-registry backend integration suite (live PostGIS, fake RustFS).

Exercises the merged T-200~T-212 source-registry services end-to-end against a
real PostGIS database (``KTG_TEST_PG_DSN``-gated, skips cleanly when unset) and an
in-memory S3-compatible fake object store, covering the backend-testable subset of
the 27 "통합 시나리오" in ``docs/t109-backup-source-upload-management.md`` (lines
~2079-2101). Pure-UI scenarios and epost (#27 depends on T-207, not merged) are
skipped with explicit reasons.

Pattern mirrors ``test_optional_real_postgres_ops_constraints.py``: a
``KTG_TEST_PG_DSN`` gate, ``make_async_engine(Settings(pg_dsn=dsn))``, a
disposable-database guard, and ``SCHEMA_SQL``/``INDEX_SQL`` via
``iter_sql_statements``. Schema application tolerates an already-applied database
(the container persists between runs); each test TRUNCATEs the ``ops.source_*``
tables for isolation.

The fake RustFS harness is an in-memory object store wired through the real
:class:`RustfsClient`: the SigV4 + multipart + list/head/delete parsing code runs
unchanged against an injected ``RustfsSender`` (so that production code path is
under test), while the two body-streaming GETs that bypass the sender
(``rehash``/``download_file``) are overridden to read the store directly.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest
from sqlalchemy import text

from kortravelgeo.core.source_validation import GroupValidation, PartValidation
from kortravelgeo.dto.source import UploadSessionCreateRequest
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.rustfs import (
    EffectiveRustfsConfig,
    RustfsClient,
)
from kortravelgeo.infra.source_group_service import (
    RegisterContext,
    RestoreChildVerification,
    SourceGroupRegistrar,
    recompute_group_aggregates,
    restore_group,
    revalidate_group,
    soft_delete_group,
)
from kortravelgeo.infra.source_match_set_service import SourceMatchSetRepository
from kortravelgeo.infra.source_reconcile import (
    resolve_reconcile_item,
    run_source_reconcile,
)
from kortravelgeo.infra.source_upload_repo import (
    SourceUploadSessionRepository,
    should_fail_storage_state,
)
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements

DSN_ENV = "KTG_TEST_PG_DSN"

#: ``ops`` tables truncated before each scenario for isolation. Order is
#: irrelevant with ``CASCADE``; audit_events is included so per-test audit
#: assertions start clean.
_TRUNCATE_TABLES = (
    "ops.source_storage_reconcile_items",
    "ops.source_storage_reconcile_runs",
    "ops.source_match_set_items",
    "ops.source_match_sets",
    "ops.source_file_members",
    "ops.source_file_validations",
    "ops.source_files",
    "ops.source_file_groups",
    "ops.source_upload_session_parts",
    "ops.source_upload_sessions",
    "ops.serving_releases",
    "ops.dataset_snapshots",
    "ops.audit_events",
)


# ---------------------------------------------------------------------------
# fake RustFS object store + sender
# ---------------------------------------------------------------------------


@dataclass
class _StoredObject:
    body: bytes
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def etag(self) -> str:
        return hashlib.md5(self.body).hexdigest()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass
class _Multipart:
    key: str
    parts: dict[int, bytes] = field(default_factory=dict)


class FakeS3Store:
    """In-memory S3-compatible store backing the fake :data:`RustfsSender`.

    Implements exactly the operations the real :class:`RustfsClient` issues:
    bucket HEAD/PUT, object PUT/HEAD/DELETE, ``ListObjectsV2``, and the multipart
    lifecycle (create/upload-part/complete/abort/ListParts). ``bucket_lost``
    simulates total bucket loss (scenario 26): every request 404s.
    """

    def __init__(self) -> None:
        self.objects: dict[str, _StoredObject] = {}
        self.multiparts: dict[str, _Multipart] = {}
        self.buckets: set[str] = set()
        self.bucket_lost = False
        self._upload_seq = 0
        self._pending_meta: dict[str, dict[str, str]] = {}

    # --- test-facing helpers ----------------------------------------------

    def put(self, key: str, body: bytes, *, metadata: dict[str, str] | None = None) -> None:
        self.objects[key] = _StoredObject(body=body, metadata=dict(metadata or {}))

    def drop(self, key: str) -> None:
        self.objects.pop(key, None)

    def orphan_multipart(self, key: str) -> str:
        """Register an in-progress multipart upload with no completed object."""
        self._upload_seq += 1
        upload_id = f"orphan-{self._upload_seq}"
        mp = _Multipart(key=key)
        mp.parts[1] = b"partial"
        self.multiparts[upload_id] = mp
        return upload_id

    # --- request dispatch --------------------------------------------------

    async def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        content: bytes | AsyncIterator[bytes] | None,
    ) -> httpx.Response:
        if self.bucket_lost:
            return _xml_error(404, "NoSuchBucket")
        parsed = urlsplit(url)
        path = parsed.path.lstrip("/")
        segments = path.split("/", 1)
        bucket = unquote(segments[0]) if segments and segments[0] else ""
        key = unquote(segments[1]) if len(segments) > 1 else ""
        query = parse_qs(parsed.query, keep_blank_values=True)
        body = await _collect_body(content)

        # ListObjectsV2 is keyed on the bucket (no object key) but distinguished
        # by the ``list-type`` query param — check it before the bucket op.
        if "list-type" in query:
            return self._list_objects(query)
        if not key:
            return self._bucket_op(method, bucket)
        if "uploads" in query:  # POST .../key?uploads
            return self._create_multipart(key, headers)
        if "uploadId" in query and "partNumber" in query:
            return self._upload_part(key, query, body)
        if "uploadId" in query and method == "POST":
            return self._complete_multipart(key, query)
        if "uploadId" in query and method == "DELETE":
            return self._abort_multipart(query)
        if "uploadId" in query and method == "GET":
            return self._list_parts(key, query)
        return self._object_op(method, key, headers, body)

    # --- bucket / object ---------------------------------------------------

    def _bucket_op(self, method: str, bucket: str) -> httpx.Response:
        if method == "HEAD":
            return httpx.Response(200 if bucket in self.buckets else 404)
        if method == "PUT":
            self.buckets.add(bucket)
            return httpx.Response(200)
        return httpx.Response(200)

    def _object_op(
        self, method: str, key: str, headers: dict[str, str], body: bytes
    ) -> httpx.Response:
        if method == "PUT":
            metadata = {
                name[len("x-amz-meta-") :]: value
                for name, value in headers.items()
                if name.lower().startswith("x-amz-meta-")
            }
            self.objects[key] = _StoredObject(body=body, metadata=metadata)
            return httpx.Response(200, headers={"etag": f'"{self.objects[key].etag}"'})
        if method == "HEAD":
            obj = self.objects.get(key)
            if obj is None:
                return httpx.Response(404)
            return httpx.Response(
                200,
                headers={
                    "content-length": str(len(obj.body)),
                    "etag": f'"{obj.etag}"',
                    **{f"x-amz-meta-{k}": v for k, v in obj.metadata.items()},
                },
            )
        if method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        if method == "GET":
            obj = self.objects.get(key)
            if obj is None:
                return _xml_error(404, "NoSuchKey")
            return httpx.Response(200, content=obj.body, headers={"etag": f'"{obj.etag}"'})
        return httpx.Response(400)

    # --- ListObjectsV2 -----------------------------------------------------

    def _list_objects(self, query: dict[str, list[str]]) -> httpx.Response:
        prefix = query.get("prefix", [""])[0]
        contents = "".join(
            f"<Contents><Key>{_xml_escape(k)}</Key><Size>{len(o.body)}</Size>"
            f'<ETag>"{o.etag}"</ETag></Contents>'
            for k, o in sorted(self.objects.items())
            if k.startswith(prefix)
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>false</IsTruncated>{contents}</ListBucketResult>"
        )
        return httpx.Response(200, content=xml.encode("utf-8"))

    # --- multipart ---------------------------------------------------------

    def _create_multipart(self, key: str, headers: dict[str, str]) -> httpx.Response:
        self._upload_seq += 1
        upload_id = f"upload-{self._upload_seq}"
        self.multiparts[upload_id] = _Multipart(key=key)
        # remember requested metadata so complete can attach it
        self.multiparts[upload_id].parts.clear()
        self._meta_for(upload_id, headers)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<InitiateMultipartUploadResult>"
            f"<UploadId>{upload_id}</UploadId></InitiateMultipartUploadResult>"
        )
        return httpx.Response(200, content=xml.encode("utf-8"))

    def _meta_for(self, upload_id: str, headers: dict[str, str]) -> None:
        self._pending_meta[upload_id] = {
            name[len("x-amz-meta-") :]: value
            for name, value in headers.items()
            if name.lower().startswith("x-amz-meta-")
        }

    def _upload_part(
        self, key: str, query: dict[str, list[str]], body: bytes
    ) -> httpx.Response:
        upload_id = query["uploadId"][0]
        part_number = int(query["partNumber"][0])
        mp = self.multiparts.get(upload_id)
        if mp is None:
            return _xml_error(404, "NoSuchUpload")
        mp.parts[part_number] = body
        etag = hashlib.md5(body).hexdigest()
        return httpx.Response(200, headers={"etag": f'"{etag}"'})

    def _complete_multipart(self, key: str, query: dict[str, list[str]]) -> httpx.Response:
        upload_id = query["uploadId"][0]
        mp = self.multiparts.pop(upload_id, None)
        if mp is None:
            return _xml_error(404, "NoSuchUpload")
        body = b"".join(mp.parts[n] for n in sorted(mp.parts))
        metadata = self._pending_meta.pop(upload_id, {})
        self.objects[key] = _StoredObject(body=body, metadata=metadata)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<CompleteMultipartUploadResult><ETag>"
            f'"{self.objects[key].etag}"</ETag></CompleteMultipartUploadResult>'
        )
        return httpx.Response(200, content=xml.encode("utf-8"))

    def _abort_multipart(self, query: dict[str, list[str]]) -> httpx.Response:
        self.multiparts.pop(query["uploadId"][0], None)
        return httpx.Response(204)

    def _list_parts(self, key: str, query: dict[str, list[str]]) -> httpx.Response:
        upload_id = query["uploadId"][0]
        mp = self.multiparts.get(upload_id)
        if mp is None:
            return _xml_error(404, "NoSuchUpload")
        parts = "".join(
            f"<Part><PartNumber>{n}</PartNumber>"
            f'<ETag>"{hashlib.md5(mp.parts[n]).hexdigest()}"</ETag>'
            f"<Size>{len(mp.parts[n])}</Size></Part>"
            for n in sorted(mp.parts)
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<ListPartsResult><IsTruncated>false</IsTruncated>{parts}</ListPartsResult>"
        )
        return httpx.Response(200, content=xml.encode("utf-8"))


class FakeRustfsClient(RustfsClient):
    """Real :class:`RustfsClient` wired to a :class:`FakeS3Store`.

    All sender-routed operations (multipart/head/list/delete/list_parts) run
    through the unmodified production code against the fake store. The two
    body-streaming GETs (``rehash``/``download_file``) bypass the sender in
    production (they build their own ``httpx.AsyncClient``), so they are
    overridden here to read the store directly — preserving the SHA-256 contract.
    """

    def __init__(self, store: FakeS3Store, *, bucket: str = "test-bucket") -> None:
        self._store = store
        config = EffectiveRustfsConfig(
            enabled=True,
            endpoint_url="http://fake-rustfs.local",
            bucket=bucket,
            prefix="ktg",
            region="us-east-1",
            force_path_style=True,
            retention_days=0,
            access_key="ak",
            secret_key="sk",
        )
        super().__init__(config, sender=store)

    async def rehash(self, key: str) -> str:
        obj = self._store.objects.get(key)
        if obj is None:
            raise FileNotFoundError(key)
        return obj.sha256

    async def compute_sha256(self, key: str) -> str:
        return await self.rehash(key)

    async def download_file(self, key: str, destination: Path) -> None:
        obj = self._store.objects.get(key)
        if obj is None:
            raise FileNotFoundError(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(obj.body)


async def _collect_body(content: bytes | AsyncIterator[bytes] | None) -> bytes:
    if content is None:
        return b""
    if isinstance(content, bytes):
        return content
    chunks: list[bytes] = []
    async for chunk in content:
        chunks.append(chunk)
    return b"".join(chunks)


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xml_error(status: int, code: str) -> httpx.Response:
    xml = f"<?xml version='1.0'?><Error><Code>{code}</Code></Error>"
    return httpx.Response(status, content=xml.encode("utf-8"))


# ---------------------------------------------------------------------------
# DB engine / schema fixtures
# ---------------------------------------------------------------------------


def _looks_like_disposable_test_database(database_name: str) -> bool:
    normalized = database_name.lower()
    return (
        "test" in normalized
        or normalized.startswith("kor_travel_geo")
        or normalized.startswith("tmp_")
    )


async def _apply_schema_idempotent(engine: AsyncEngine) -> None:
    """Apply SCHEMA_SQL + INDEX_SQL, tolerating an already-applied database.

    The disposable container persists between test runs, so a second apply hits
    non-idempotent statements (e.g. ``ALTER TABLE ... ADD CONSTRAINT``). Each
    statement runs in its own nested transaction; "already exists" duplicate
    errors are swallowed so re-running the suite stays green.
    """
    from sqlalchemy.exc import ProgrammingError

    for sql_block in (SCHEMA_SQL, INDEX_SQL):
        for sql in iter_sql_statements(sql_block):
            async with engine.connect() as conn:
                try:
                    await conn.execution_options(isolation_level="AUTOCOMMIT")
                    await conn.execute(text(sql))
                except ProgrammingError as exc:
                    if "already exists" not in str(exc).lower():
                        raise


@pytest.fixture(scope="module")
async def engine() -> AsyncIterator[AsyncEngine]:
    dsn = os.getenv(DSN_ENV)
    if not dsn:
        pytest.skip(f"set {DSN_ENV} to a disposable PostGIS-enabled test database")
    eng = make_async_engine(Settings(pg_dsn=dsn))
    async with eng.connect() as conn:
        database_name = await conn.scalar(text("SELECT current_database()"))
        available = (
            await conn.execute(
                text(
                    "SELECT name FROM pg_available_extensions "
                    "WHERE name IN ('postgis','pg_trgm','unaccent','pg_stat_statements')"
                )
            )
        ).scalars().all()
    if database_name is None or not _looks_like_disposable_test_database(str(database_name)):
        await eng.dispose()
        pytest.skip(f"{DSN_ENV} must point to a disposable test database; got {database_name!r}")
    missing = {"postgis", "pg_trgm", "unaccent", "pg_stat_statements"} - set(available)
    if missing:
        await eng.dispose()
        pytest.skip(f"PostGIS test database missing extensions: {', '.join(sorted(missing))}")
    await _apply_schema_idempotent(eng)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Per-test isolation: TRUNCATE the source tables before handing back the engine."""
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE " + ", ".join(_TRUNCATE_TABLES) + " CASCADE"))
    yield engine


@pytest.fixture
def store() -> FakeS3Store:
    return FakeS3Store()


@pytest.fixture
def rustfs(store: FakeS3Store) -> FakeRustfsClient:
    return FakeRustfsClient(store)


# ---------------------------------------------------------------------------
# composition helpers (seed session -> register group -> build/activate set)
# ---------------------------------------------------------------------------

_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _object_key(prefix: str, session_id: str, part_key: str) -> str:
    return f"{prefix}/uploads/{session_id}/{part_key}"


def _passed_validation(category: str, *part_keys: str) -> GroupValidation:
    keys = part_keys or ("archive",)
    return GroupValidation(
        category=category,
        outcome="passed",
        parts=tuple(PartValidation(part_key=k, outcome="passed") for k in keys),
        coverage=dict.fromkeys(keys, "present"),
    )


async def _seed_session(
    engine: AsyncEngine,
    *,
    category: str = "locsum_full",
    user_yyyymm: str = "202604",
    prefix: str = "ktg",
) -> tuple[str, str]:
    """Create an upload session; return ``(session_id, source_file_group_id)``."""
    repo = SourceUploadSessionRepository(engine)
    result = await repo.create_session(
        UploadSessionCreateRequest(
            category=category, user_yyyymm=user_yyyymm, display_name=f"{category} test"
        ),
        bucket="test-bucket",
        prefix=prefix,
    )
    return result.session.upload_session_id, result.session.source_file_group_id


async def _register_single_file_group(
    engine: AsyncEngine,
    store: FakeS3Store,
    *,
    category: str = "locsum_full",
    user_yyyymm: str = "202604",
    sha256: str = _SHA_A,
    body: bytes = b"locsum-archive-bytes",
    prefix: str = "ktg",
) -> tuple[str, str]:
    """Seed + register a single-file group with its object stored. Returns ids."""
    session_id, group_id = await _seed_session(
        engine, category=category, user_yyyymm=user_yyyymm, prefix=prefix
    )
    object_key = _object_key(prefix, session_id, "archive")
    store.put(object_key, body)
    real_sha = sha256
    ctx = RegisterContext(
        part_key="archive",
        part_kind="single",
        part_label=None,
        original_filename=f"{category}.zip",
        sha256=real_sha,
        size_bytes=len(body),
        object_key=object_key,
        object_etag=store.objects[object_key].etag,
        compression_format="zip",
    )
    registrar = SourceGroupRegistrar(engine)
    await registrar.register(
        session_id=session_id,
        contexts=(ctx,),
        structure_validation=_passed_validation(category),
        storage_kind="rustfs",
        bucket="test-bucket",
        actor="tester",
        yyyymm_mismatch_ack=False,
    )
    return session_id, group_id


async def _build_validated_match_set(
    engine: AsyncEngine,
    *,
    group_id: str,
    category: str = "locsum_full",
    name: str = "ms",
) -> str:
    """Create a draft match set referencing ``group_id`` and validate it."""
    from kortravelgeo.dto.source import (
        SourceMatchSetCreateRequest,
        SourceMatchSetItemRequest,
    )

    repo = SourceMatchSetRepository(engine)
    detail = await repo.create_match_set(
        SourceMatchSetCreateRequest(
            name=name,
            profile="custom",
            items=(
                SourceMatchSetItemRequest(
                    category=category,
                    role="build_required",
                    source_file_group_id=group_id,
                    effective_yyyymm="202604",
                ),
            ),
        ),
        actor="tester",
    )
    msid = detail.match_set.source_match_set_id
    resp = await repo.validate_match_set(msid, actor="tester")
    assert resp.ok, resp.reasons
    return msid


async def _group_state(engine: AsyncEngine, group_id: str) -> tuple[str, str, str | None]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT state, validation_state, group_sha256 "
                    "FROM ops.source_file_groups WHERE source_file_group_id = :gid"
                ),
                {"gid": group_id},
            )
        ).mappings().one()
    return str(row["state"]), str(row["validation_state"]), row["group_sha256"]


async def _match_set_state(engine: AsyncEngine, msid: str) -> tuple[str, bool]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT state, integrity_alert FROM ops.source_match_sets "
                    "WHERE source_match_set_id = :id"
                ),
                {"id": msid},
            )
        ).mappings().one()
    return str(row["state"]), bool(row["integrity_alert"])


async def _set_match_set_state(engine: AsyncEngine, msid: str, state: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops.source_match_sets SET state = :state WHERE source_match_set_id = :id"
            ),
            {"id": msid, "state": state},
        )


# ===========================================================================
# Scenario 1/2: roadname/locsum fixture upload -> register
# ===========================================================================


async def test_s01_s02_register_single_file_group_available(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#1/#2: single-file fixture upload → group/file registry; group available."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    state, vstate, sha = await _group_state(db, group_id)
    assert state == "available"
    assert vstate == "passed"
    assert sha is not None and len(sha) == 64

    async with db.connect() as conn:
        files = (
            await conn.execute(
                text(
                    "SELECT state, validation_state, object_key, sha256 "
                    "FROM ops.source_files WHERE source_file_group_id = :gid"
                ),
                {"gid": group_id},
            )
        ).mappings().all()
        outcome = await conn.scalar(
            text("SELECT outcome FROM ops.audit_events WHERE action = 'source_upload.register'")
        )
    assert len(files) == 1
    assert files[0]["state"] == "available"
    # the fix under test: domain outcomes map onto the audit lifecycle enum.
    assert outcome == "succeeded"


# ===========================================================================
# Scenario 4: RustFS fake client object metadata round-trip (real multipart)
# ===========================================================================


async def test_s04_rustfs_fake_multipart_head_list_roundtrip(
    rustfs: FakeRustfsClient, store: FakeS3Store
) -> None:
    """#4: the fake store drives the REAL RustfsClient multipart/head/list/rehash."""
    key = "ktg/uploads/sess/archive"
    upload_id = await rustfs.create_multipart_upload(key, metadata={"category": "locsum_full"})
    part = await rustfs.upload_part(key, upload_id=upload_id, part_number=1, body=b"hello-world")
    etag = await rustfs.complete_multipart_upload(key, upload_id=upload_id, parts=(part,))
    assert etag

    head = await rustfs.head_object(key)
    assert head.size == len(b"hello-world")
    assert head.metadata["category"] == "locsum_full"
    listed = await rustfs.list_objects("ktg/")
    assert any(o.key == key for o in listed)
    assert await rustfs.rehash(key) == hashlib.sha256(b"hello-world").hexdigest()

    await rustfs.delete_object(key)
    assert key not in store.objects


# ===========================================================================
# Scenario 5: object deleted -> reconcile db_missing_object
# ===========================================================================


async def test_s05_reconcile_db_missing_object(
    db: AsyncEngine, store: FakeS3Store, rustfs: FakeRustfsClient
) -> None:
    """#5: registered object deleted in storage → reconcile db_missing_object."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    async with db.connect() as conn:
        object_key = await conn.scalar(
            text("SELECT object_key FROM ops.source_files WHERE source_file_group_id = :gid"),
            {"gid": group_id},
        )
    store.drop(str(object_key))

    result = await run_source_reconcile(
        db, rustfs=rustfs, prefix="ktg", mode="quick", actor="tester", rolling_deep_days=30
    )
    assert result.issue_counts.get("db_missing_object", 0) >= 1
    # the file row is marked missing (a single-object loss is not mass-loss, so the
    # group aggregate is not recomputed by reconcile — that is the documented path).
    async with db.connect() as conn:
        file_state = await conn.scalar(
            text("SELECT state FROM ops.source_files WHERE source_file_group_id = :gid"),
            {"gid": group_id},
        )
    assert file_state == "missing"


# ===========================================================================
# Scenario 6: unregistered stored object -> reconcile object_missing_db
# ===========================================================================


async def test_s06_reconcile_object_missing_db(
    db: AsyncEngine, store: FakeS3Store, rustfs: FakeRustfsClient
) -> None:
    """#6: a stored object with no DB row and no session → object_missing_db."""
    store.put("ktg/uploads/ghost/archive", b"orphan-bytes")
    result = await run_source_reconcile(
        db, rustfs=rustfs, prefix="ktg", mode="quick", actor="tester", rolling_deep_days=30
    )
    assert result.issue_counts.get("object_missing_db", 0) >= 1


# ===========================================================================
# Scenario 7: orphaned multipart (no completed object) -> still object_missing_db
#   (run_source_reconcile classifies stored objects; an in-progress multipart has
#    no object yet — covered structurally by the janitor abort path in #15.)
# ===========================================================================


async def test_s07_orphaned_multipart_abort_via_listparts(
    rustfs: FakeRustfsClient, store: FakeS3Store
) -> None:
    """#7: an in-progress multipart with no completed object can be listed + aborted."""
    key = "ktg/uploads/orphan-sess/archive"
    upload_id = store.orphan_multipart(key)
    parts = await rustfs.list_parts(key, upload_id=upload_id)
    assert parts and parts[0].part_number == 1
    assert key not in store.objects  # not completed
    await rustfs.abort_multipart_upload(key, upload_id=upload_id)
    assert upload_id not in store.multiparts


# ===========================================================================
# Scenario 8: DB has parts but RustFS multipart upload id gone -> failed_storage_state
# ===========================================================================


async def test_s08_failed_storage_state_when_multipart_upload_gone(
    rustfs: FakeRustfsClient, store: FakeS3Store
) -> None:
    """#8: ListParts 404 (upload id gone) → slot must go failed_storage_state."""
    from kortravelgeo.exceptions import NotFoundError

    key = "ktg/uploads/sess/archive"
    recorded = frozenset({1, 2, 3})
    # upload id no longer exists in storage
    with pytest.raises(NotFoundError):
        await rustfs.list_parts(key, upload_id="does-not-exist")
    # the pure resume decision: None listed parts (404) => fail the slot.
    assert (
        should_fail_storage_state(recorded_part_numbers=recorded, listed_part_numbers=None)
        is True
    )
    # and a stale subset also fails it.
    assert (
        should_fail_storage_state(
            recorded_part_numbers=recorded, listed_part_numbers=frozenset({1, 2})
        )
        is True
    )


# ===========================================================================
# Scenario 9: child missing -> recompute propagation
#   active -> integrity_alert; non-active validated -> invalid
# ===========================================================================


async def test_s09_recompute_down_propagation(db: AsyncEngine, store: FakeS3Store) -> None:
    """#9: a group going bad flips non-active validated→invalid, active→integrity_alert."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")

    # validated (non-active) match set
    validated = await _build_validated_match_set(db, group_id=group_id, name="ms-validated")
    # a second, active match set on the same group
    active = await _build_validated_match_set(db, group_id=group_id, name="ms-active")
    await _set_match_set_state(db, active, "active")

    # mark the child missing -> group bad -> recompute propagates
    async with db.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops.source_files SET state = 'missing' "
                "WHERE source_file_group_id = :gid"
            ),
            {"gid": group_id},
        )
        await recompute_group_aggregates(conn, group_id, trigger="test")

    v_state, _ = await _match_set_state(db, validated)
    a_state, a_alert = await _match_set_state(db, active)
    assert v_state == "invalid"
    assert (a_state, a_alert) == ("active", True)


# ===========================================================================
# Scenario 9b: recovery -> invalid -> revalidatable
# ===========================================================================


async def test_s09b_recompute_up_propagation_invalid_to_revalidatable(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#9/#16: recovered group flips a non-active invalid set → revalidatable."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    msid = await _build_validated_match_set(db, group_id=group_id, name="ms")
    await _set_match_set_state(db, msid, "invalid")

    # group is already available; recompute should up-propagate.
    async with db.begin() as conn:
        await recompute_group_aggregates(conn, group_id, trigger="test_recover")
    state, _ = await _match_set_state(db, msid)
    assert state == "revalidatable"


# ===========================================================================
# Scenario 10/11: match set create -> validate (success) + optional omitted skip
# ===========================================================================


async def test_s10_s11_match_set_validate_with_omitted_optional(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#10: validate a draft → validated; #11: an omitted optional item is skipped."""
    from kortravelgeo.dto.source import (
        SourceMatchSetCreateRequest,
        SourceMatchSetItemRequest,
    )

    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    repo = SourceMatchSetRepository(db)
    detail = await repo.create_match_set(
        SourceMatchSetCreateRequest(
            name="ms-omit",
            profile="custom",
            items=(
                SourceMatchSetItemRequest(
                    category="locsum_full",
                    role="build_required",
                    source_file_group_id=group_id,
                    effective_yyyymm="202604",
                ),
                SourceMatchSetItemRequest(
                    category="detail_address_db_full",
                    role="validation_optional",
                    omitted=True,
                    omitted_reason="not uploaded this cycle",
                ),
            ),
        ),
        actor="tester",
    )
    msid = detail.match_set.source_match_set_id
    resp = await repo.validate_match_set(msid, actor="tester")
    assert resp.ok
    assert resp.state == "validated"
    assert resp.source_set_hash and len(resp.source_set_hash) == 64


# ===========================================================================
# Scenario 16 (core): activate atomic swap -> exactly one active
# ===========================================================================


async def test_s16_activate_atomic_swap_one_active(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#16: activating a second match set retires the first; never two active."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    first = await _build_validated_match_set(db, group_id=group_id, name="ms-first")
    second = await _build_validated_match_set(db, group_id=group_id, name="ms-second")

    repo = SourceMatchSetRepository(db)
    await repo.activate_match_set(first, actor="tester")
    resp = await repo.activate_match_set(second, actor="tester")
    assert resp.state == "active"
    assert resp.retired_match_set_id == first

    async with db.connect() as conn:
        active_count = await conn.scalar(
            text("SELECT count(*) FROM ops.source_match_sets WHERE state = 'active'")
        )
    assert active_count == 1
    assert (await _match_set_state(db, first))[0] == "retired"
    assert (await _match_set_state(db, second))[0] == "active"


# ===========================================================================
# Scenario 16b: active integrity_alert recovery -> validate-in-place clears it
# ===========================================================================


async def test_s16b_active_integrity_alert_validate_in_place_recovery(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#16: active set with integrity_alert → re-attach object → validate-in-place clears alert."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    msid = await _build_validated_match_set(db, group_id=group_id, name="ms")
    repo = SourceMatchSetRepository(db)
    await repo.activate_match_set(msid, actor="tester")

    # break the group -> active gets integrity_alert
    async with db.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops.source_files SET state = 'missing' "
                "WHERE source_file_group_id = :gid"
            ),
            {"gid": group_id},
        )
        await recompute_group_aggregates(conn, group_id, trigger="break")
    assert (await _match_set_state(db, msid)) == ("active", True)

    # recover the group (object re-attached / re-validated)
    async with db.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops.source_files SET state = 'available', validation_state = 'passed' "
                "WHERE source_file_group_id = :gid"
            ),
            {"gid": group_id},
        )
        await recompute_group_aggregates(conn, group_id, trigger="recover")
    # still active+alert until validate-in-place finalizes it.
    assert (await _match_set_state(db, msid)) == ("active", True)

    resp = await repo.validate_match_set(msid, actor="tester")
    assert resp.action == "validate_in_place"
    assert resp.ok
    assert (await _match_set_state(db, msid)) == ("active", False)


# ===========================================================================
# Scenario 20: concurrent create -> second is 409 conflict resume payload
# ===========================================================================


async def test_s20_duplicate_session_returns_conflict(db: AsyncEngine) -> None:
    """#20: a second create for the same (category, user_yyyymm) → 409 resume payload."""
    repo = SourceUploadSessionRepository(db)
    req = UploadSessionCreateRequest(
        category="locsum_full", user_yyyymm="202604", display_name="dup test"
    )
    first = await repo.create_session(req, bucket="test-bucket", prefix="ktg")
    second = await repo.create_session(req, bucket="test-bucket", prefix="ktg")
    assert first.conflict is False
    assert second.conflict is True
    assert second.session.upload_session_id == first.session.upload_session_id


# ===========================================================================
# Scenario 21: replace a completed slot before register invalidates it
# ===========================================================================


async def test_s21_replace_slot_before_register(db: AsyncEngine) -> None:
    """#21: replacing a completed slot drops its parts and reopens the session."""
    repo = SourceUploadSessionRepository(db)
    result = await repo.create_session(
        UploadSessionCreateRequest(
            category="locsum_full", user_yyyymm="202604", display_name="replace"
        ),
        bucket="test-bucket",
        prefix="ktg",
    )
    sid = result.session.upload_session_id
    await repo.record_part(
        sid, part_key="archive", part_number=1, part_etag="e1", received_bytes=10, completed=True
    )
    before = await repo.slot_parts(sid, part_key="archive")
    assert before and before[0].completed_at is not None

    removed = await repo.replace_slot(sid, part_key="archive")
    assert removed == 1
    after = await repo.slot_parts(sid, part_key="archive")
    assert after == ()
    session = await repo.get_session(sid)
    assert session is not None
    assert session.state == "created"


# ===========================================================================
# Scenario 22: soft-delete (active-ref guard) + restore
# ===========================================================================


async def test_s22_soft_delete_blocked_by_active_ref_then_restore(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#22: an active-referenced group cannot be soft-deleted; otherwise delete+restore works."""
    from kortravelgeo.exceptions import ConflictError

    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    msid = await _build_validated_match_set(db, group_id=group_id, name="ms")
    repo = SourceMatchSetRepository(db)
    await repo.activate_match_set(msid, actor="tester")

    # guarded: active match set references this group
    with pytest.raises(ConflictError):
        await soft_delete_group(db, group_id, actor="tester")

    # retire the active set, then soft-delete succeeds
    await repo.retire_match_set(msid, actor="tester")
    resp = await soft_delete_group(db, group_id, actor="tester")
    assert resp.state == "soft_deleted"

    # restore with a present, consistent object -> validating/available
    async with db.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT source_file_id, part_key, sha256, size_bytes "
                    "FROM ops.source_files WHERE source_file_group_id = :gid"
                ),
                {"gid": group_id},
            )
        ).mappings().all()
    verifications = tuple(
        RestoreChildVerification(
            source_file_id=str(r["source_file_id"]),
            part_key=str(r["part_key"]),
            object_present=True,
            observed_sha256=str(r["sha256"]),
            observed_size=int(r["size_bytes"]),
        )
        for r in rows
    )
    restore_resp = await restore_group(db, group_id, verifications=verifications, actor="tester")
    assert restore_resp.state in {"available", "validating"}
    assert restore_resp.files and restore_resp.files[0].state in {"available", "validating"}


# ===========================================================================
# Scenario 23: registration deadline passed -> registration_expired (janitor)
# ===========================================================================


async def test_s23_registration_expired_janitor(db: AsyncEngine) -> None:
    """#23: a stored-but-unregistered session past its deadline → registration_expired."""
    from kortravelgeo.infra.source_janitor import run_source_upload_janitor

    repo = SourceUploadSessionRepository(db)
    result = await repo.create_session(
        UploadSessionCreateRequest(
            category="locsum_full", user_yyyymm="202604", display_name="expire"
        ),
        bucket="test-bucket",
        prefix="ktg",
    )
    sid = result.session.upload_session_id
    # the single archive slot is completed (stored to RustFS) but never registered.
    await repo.record_part(
        sid, part_key="archive", part_number=1, part_etag="e", received_bytes=10, completed=True
    )
    async with db.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops.source_upload_sessions "
                "SET state = 'pending_registration', uploaded_file_count = 1, "
                "    registration_deadline_at = now() - interval '1 day' "
                "WHERE source_upload_session_id = :sid"
            ),
            {"sid": sid},
        )

    summary = await run_source_upload_janitor(
        db, rustfs=None, ttl_days=7, deadline_days=30, now=datetime.now(UTC)
    )
    assert summary.registration_expired >= 1
    session = await repo.get_session(sid)
    assert session is not None
    assert session.state == "registration_expired"


# ===========================================================================
# Scenario 26: full bucket loss -> active integrity_alert, non-active validated invalid
# ===========================================================================


async def test_s26_bucket_loss_mass_loss_propagation(
    db: AsyncEngine, store: FakeS3Store, rustfs: FakeRustfsClient
) -> None:
    """#26: total bucket loss → mass-loss reconcile flips active→alert, validated→invalid."""
    # three groups so the mass-loss threshold (>=3 files, >=90% missing) is met.
    group_ids: list[str] = []
    for i in range(3):
        _, gid = await _register_single_file_group(
            db,
            store,
            category="locsum_full",
            user_yyyymm=f"20260{i + 1}",
            body=f"archive-{i}".encode(),
        )
        group_ids.append(gid)

    active = await _build_validated_match_set(
        db, group_id=group_ids[0], name="ms-active"
    )
    await _set_match_set_state(db, active, "active")
    validated = await _build_validated_match_set(
        db, group_id=group_ids[1], name="ms-validated"
    )

    # Total source loss: every registered object is gone (list returns empty).
    # The reconcile mass-loss assessment (>=3 scanned files, >=90% missing) fires
    # and recomputes every affected group, propagating to referencing match sets.
    store.objects.clear()
    result = await run_source_reconcile(
        db, rustfs=rustfs, prefix="ktg", mode="quick", actor="tester", rolling_deep_days=30
    )
    assert result.mass_loss is True

    assert (await _match_set_state(db, active)) == ("active", True)
    assert (await _match_set_state(db, validated))[0] == "invalid"


# ===========================================================================
# Scenario 5b: reconcile resolve guard (mark_db_missing on a reappeared object)
# ===========================================================================


async def test_s05b_reconcile_resolve_and_stale_guard(
    db: AsyncEngine, store: FakeS3Store, rustfs: FakeRustfsClient
) -> None:
    """#5/#16: resolve a db_missing_object item; a reappeared object makes it stale."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    async with db.connect() as conn:
        object_key = await conn.scalar(
            text("SELECT object_key FROM ops.source_files WHERE source_file_group_id = :gid"),
            {"gid": group_id},
        )
    body = store.objects[str(object_key)].body
    store.drop(str(object_key))

    run = await run_source_reconcile(
        db, rustfs=rustfs, prefix="ktg", mode="quick", actor="tester", rolling_deep_days=30
    )
    async with db.connect() as conn:
        item_id = await conn.scalar(
            text(
                "SELECT source_storage_reconcile_item_id "
                "FROM ops.source_storage_reconcile_items "
                "WHERE source_storage_reconcile_run_id = :rid AND issue_type = 'db_missing_object' "
                "LIMIT 1"
            ),
            {"rid": run.source_storage_reconcile_run_id},
        )
    assert item_id is not None

    # object reappears -> mark_db_missing should be guarded as stale (ignored):
    # the re-resolve recheck sees the object present again and refuses the action.
    store.put(str(object_key), body)
    resp = await resolve_reconcile_item(
        db, str(item_id), action="mark_db_missing", actor="tester", rustfs=rustfs
    )
    assert resp.state == "ignored"
    # the stale-guard returns early WITHOUT mutating the DB: the item row stays
    # 'open' (so it can be re-evaluated) and the run's resolved_count is not bumped.
    async with db.connect() as conn:
        item_state = await conn.scalar(
            text(
                "SELECT state FROM ops.source_storage_reconcile_items "
                "WHERE source_storage_reconcile_item_id = :id"
            ),
            {"id": str(item_id)},
        )
        resolved_count = await conn.scalar(
            text(
                "SELECT resolved_count FROM ops.source_storage_reconcile_runs "
                "WHERE source_storage_reconcile_run_id = :rid"
            ),
            {"rid": run.source_storage_reconcile_run_id},
        )
    assert item_state == "open"
    assert resolved_count == 0


# ===========================================================================
# Scenario 13: run-validation source-integrity mismatch (revalidate not silently skipped)
# ===========================================================================


async def test_s13_revalidate_failed_marks_invalid_not_skipped(
    db: AsyncEngine, store: FakeS3Store
) -> None:
    """#13: a structure-failed revalidate folds to failed/quarantined, not skipped."""
    _, group_id = await _register_single_file_group(db, store, category="locsum_full")
    failed = GroupValidation(
        category="locsum_full",
        outcome="failed",
        parts=(
            PartValidation(
                part_key="archive", outcome="failed", reasons=("필수 member 누락",)
            ),
        ),
        coverage={"archive": "failed"},
    )
    result = await revalidate_group(db, group_id, decision=failed, actor="tester")
    # the key #13 guarantee: a structure-failed revalidate is recorded as 'failed',
    # NOT silently misclassified as 'skipped'. (The group does not become available.)
    assert result.validation_state == "failed"
    assert result.validation_state != "skipped"
    assert result.state != "available"


# ===========================================================================
# Explicit skips: scenarios outside the backend-testable / merged scope
# ===========================================================================


@pytest.mark.skip(
    reason="#27 epost fetch depends on T-207 (epost server-fetch flow), NOT merged"
)
def test_s27_epost_fetch_skipped() -> None:  # pragma: no cover
    ...


@pytest.mark.skip(
    reason="#3 multi_part slot-coverage UI + #12/#18/#19 rebuild loader DAG and "
    "#14/#24/#25 restore stub require the loader/RustFS materialization bridge "
    "(SourceRebuildService.prepare_rebuild enqueues the full_load_batch DAG) and "
    "the verify/restore client layer that materializes archives; those are "
    "exercised by the rebuild/restore service unit tests and the API layer, not "
    "this DB+fake-store backend slice. Pure-UI scenarios (3/11-UI) are frontend tests."
)
def test_rebuild_and_restore_dag_scenarios_skipped() -> None:  # pragma: no cover
    ...
