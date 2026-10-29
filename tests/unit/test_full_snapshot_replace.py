from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.source_rebuild_service import RebuildGroupRef, SourceRebuildService
from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
from kortravelgeo.loaders.text.locsum_loader import load_locsum
from kortravelgeo.loaders.text.navi_loader import load_navi

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", [load_juso_hangul, load_locsum, load_navi])
async def test_partial_input_cannot_replace_a_full_snapshot(loader: Any, tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="limit_per_file"):
        await loader(
            cast("Any", object()), tmp_path, source_yyyymm="202609", limit_per_file=1, replace=True
        )


def test_registry_rebuild_explicitly_replaces_full_snapshot_tables() -> None:
    ref = RebuildGroupRef(
        category="roadname_hangul_full", source_file_group_id="g-1", group_sha256="a" * 64,
        user_yyyymm="202609", effective_yyyymm="202609",
        load_kinds=("juso_text_load", "juso_parcel_link_load"),
        object_keys=(), file_ids=(), storage_uris=(), files=(),
    )
    plan = SourceRebuildService(cast("Any", object()))._assemble_plan("ms-1", (ref,))
    assert all(child["payload"].get("replace") is True for child in plan.batch_payload["children"])
