"""T-238 live DB/RustFS manifest source reconcile (opt-in).

Default CI skips this test. To run it, provide a DB DSN, enable the explicit live
gate, and point to a backup ``manifest.json`` that contains ``source_match_set``:

    KTG_TEST_PG_DSN=postgresql+psycopg://... \
    KTG_TEST_RUSTFS_SOURCE_RECONCILE=1 \
    KTG_TEST_BACKUP_MANIFEST=/path/to/manifest.json \
        pytest tests/integration/test_t238_manifest_source_reconcile_live.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kortravelgeo.infra.backup import read_json
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.rustfs import RustfsClient, require_enabled_rustfs
from kortravelgeo.infra.source_restore_service import reconcile_manifest_source_inventory
from kortravelgeo.settings import Settings


@pytest.mark.asyncio
async def test_live_manifest_source_reconcile_opt_in() -> None:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    manifest_path = os.getenv("KTG_TEST_BACKUP_MANIFEST")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to run live T-238 reconcile")
    if os.getenv("KTG_TEST_RUSTFS_SOURCE_RECONCILE") != "1":
        pytest.skip("set KTG_TEST_RUSTFS_SOURCE_RECONCILE=1 to allow live RustFS HEAD")
    if not manifest_path:
        pytest.skip("set KTG_TEST_BACKUP_MANIFEST to a backup manifest.json")

    settings = Settings(pg_dsn=dsn)
    engine = make_async_engine(settings)
    try:
        manifest = read_json(Path(manifest_path))
        rustfs = RustfsClient(require_enabled_rustfs(settings))
        report = await reconcile_manifest_source_inventory(
            engine,
            manifest,
            rustfs=rustfs,
            actor=None,
        )
    finally:
        await engine.dispose()

    assert report.skipped is False
    assert report.total > 0
