from __future__ import annotations

import inspect

from kraddr.geo.loaders.text import locsum_loader


def test_locsum_upsert_deduplicates_staging_rows_before_on_conflict() -> None:
    source = inspect.getsource(locsum_loader.copy_locsum_rows)

    assert "SELECT DISTINCT ON (sig_cd, ent_man_no)" in source
    assert "ORDER BY sig_cd, ent_man_no" in source
    assert "staging_seq BIGSERIAL" in source
    assert "staging_seq DESC" in source
    assert "ctid DESC" not in source
    assert "ON CONFLICT (sig_cd, ent_man_no) DO UPDATE" in source
