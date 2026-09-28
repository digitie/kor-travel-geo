"""T-312 pre-provisioned extension/schema TOC filter for non-superuser pg_restore.

The listing below is real ``pg_restore -l`` output (PG16.9 server / pg_dump 16.14) of a dump
taken by a NOSUPERUSER/NOCREATEDB app role on a DB whose ``x_extension`` schema and extensions
were created by the cluster admin — the shared-instance layout (T-308). Restoring it as that
app role without the filter failed with ``must be owner of extension``/``must be owner of
schema x_extension``/``schema "x_extension" already exists``/``permission denied for table
spatial_ref_sys``; with exactly these entries commented out it exited 0.
"""

from __future__ import annotations

from kortravelgeo.infra.restore_toc import filter_preprovisioned_toc

_SHARED_INSTANCE_TOC = [
    ";",
    "; Archive created at 2026-09-29 06:54:09 KST",
    ";     dbname: kor_travel_geo",
    ";     Dumped from database version: 16.9 (Debian 16.9-1.pgdg110+1)",
    ";",
    "; Selected TOC Entries:",
    ";",
    "11; 2615 21179 SCHEMA - ops kor_travel_geo_app",
    "10; 2615 19715 SCHEMA - x_extension shared_admin",
    "5053; 0 0 ACL - SCHEMA x_extension shared_admin",
    "5; 3079 20886 EXTENSION - pg_stat_statements ",
    "5054; 0 0 COMMENT - EXTENSION pg_stat_statements ",
    "3; 3079 20798 EXTENSION - pg_trgm ",
    "5055; 0 0 COMMENT - EXTENSION pg_trgm ",
    "2; 3079 19716 EXTENSION - postgis ",
    "5056; 0 0 COMMENT - EXTENSION postgis ",
    "4; 3079 20879 EXTENSION - unaccent ",
    "5057; 0 0 COMMENT - EXTENSION unaccent ",
    "275; 1259 21656 TABLE ops public_api_keys kor_travel_geo_app",
    "252; 1259 21170 TABLE public geo_cache kor_travel_geo_app",
    "276; 1259 21754 MATERIALIZED VIEW public mv_geocode_target kor_travel_geo_app",
    "246; 1259 21121 SEQUENCE public postal_bulk_delivery_bulk_id_seq kor_travel_geo_app",
    "5058; 0 0 SEQUENCE OWNED BY public postal_bulk_delivery_bulk_id_seq kor_travel_geo_app",
    "4367; 0 20038 TABLE DATA x_extension spatial_ref_sys shared_admin",
    "4368; 0 21170 TABLE DATA public geo_cache kor_travel_geo_app",
    "4114; 2606 36201 CONSTRAINT public tl_juso_text tl_juso_text_pkey kor_travel_geo_app",
    "4400; 1259 36300 INDEX public ix_mv_geocode_target_pt_5179 kor_travel_geo_app",
    "4500; 0 36400 MATERIALIZED VIEW DATA public mv_geocode_target kor_travel_geo_app",
]

_ADMIN_EXTENSIONS = ("pg_stat_statements", "pg_trgm", "plpgsql", "postgis", "unaccent")

_EXPECTED_SKIPPED = {
    "10; 2615 19715 SCHEMA - x_extension shared_admin",
    "5053; 0 0 ACL - SCHEMA x_extension shared_admin",
    "5; 3079 20886 EXTENSION - pg_stat_statements",
    "5054; 0 0 COMMENT - EXTENSION pg_stat_statements",
    "3; 3079 20798 EXTENSION - pg_trgm",
    "5055; 0 0 COMMENT - EXTENSION pg_trgm",
    "2; 3079 19716 EXTENSION - postgis",
    "5056; 0 0 COMMENT - EXTENSION postgis",
    "4; 3079 20879 EXTENSION - unaccent",
    "5057; 0 0 COMMENT - EXTENSION unaccent",
    "4367; 0 20038 TABLE DATA x_extension spatial_ref_sys shared_admin",
}


def test_shared_instance_listing_skips_exactly_the_admin_provisioned_entries() -> None:
    result = filter_preprovisioned_toc(
        _SHARED_INSTANCE_TOC, extensions=_ADMIN_EXTENSIONS, schemas=("x_extension",)
    )

    assert set(result.skipped_entries) == _EXPECTED_SKIPPED
    assert len(result.lines) == len(_SHARED_INSTANCE_TOC)
    for original, written in zip(_SHARED_INSTANCE_TOC, result.lines, strict=True):
        if original.strip() in _EXPECTED_SKIPPED:
            # commented out (pg_restore --use-list skips ';' lines), otherwise verbatim
            assert written == f";{original}"
        else:
            assert written == original


def test_app_objects_and_data_are_never_skipped() -> None:
    result = filter_preprovisioned_toc(
        _SHARED_INSTANCE_TOC, extensions=_ADMIN_EXTENSIONS, schemas=("x_extension",)
    )

    kept = [line for line in result.lines if not line.startswith(";")]
    assert "11; 2615 21179 SCHEMA - ops kor_travel_geo_app" in kept
    assert "4368; 0 21170 TABLE DATA public geo_cache kor_travel_geo_app" in kept
    assert any("MATERIALIZED VIEW DATA public mv_geocode_target" in line for line in kept)
    assert not any("x_extension" in line or "EXTENSION -" in line for line in kept)


def test_extension_name_prefix_does_not_match_a_longer_extension() -> None:
    lines = [
        "7; 3079 1 EXTENSION - postgis_topology ",
        "8; 0 0 COMMENT - EXTENSION postgis_topology ",
        "9; 3079 2 EXTENSION - postgis ",
    ]

    result = filter_preprovisioned_toc(lines, extensions=("postgis",), schemas=())

    assert result.skipped_entries == ("9; 3079 2 EXTENSION - postgis",)


def test_owned_extensions_and_other_schemas_are_kept() -> None:
    """Only what the target reports as unmanageable is skipped (a superuser target → nothing)."""
    result = filter_preprovisioned_toc(_SHARED_INSTANCE_TOC, extensions=(), schemas=())

    assert result.skipped_entries == ()
    assert result.lines == tuple(_SHARED_INSTANCE_TOC)


def test_public_is_never_filtered_as_a_schema_even_if_it_holds_an_extension() -> None:
    """Filtering ``public`` wholesale would silently drop every serving table from the restore."""
    lines = [
        "20; 3079 1 EXTENSION - postgis ",
        "21; 1259 2 TABLE public tl_juso_text kor_travel_geo_app",
        "22; 0 2 TABLE DATA public tl_juso_text kor_travel_geo_app",
        "23; 0 0 ACL - SCHEMA public pg_database_owner",
    ]

    result = filter_preprovisioned_toc(lines, extensions=("postgis",), schemas=("public",))

    assert result.skipped_entries == ("20; 3079 1 EXTENSION - postgis",)


def test_schema_filter_matches_namespace_not_names_that_mention_it() -> None:
    lines = [
        "30; 1255 1 FUNCTION public f(x_extension.geometry) kor_travel_geo_app",
        "31; 0 0 COMMENT - SCHEMA x_extension shared_admin",
        "32; 0 0 ACL x_extension TABLE spatial_ref_sys shared_admin",
        "33; 0 1 SEQUENCE SET x_extension topology_id_seq shared_admin",
    ]

    result = filter_preprovisioned_toc(lines, extensions=(), schemas=("x_extension",))

    assert set(result.skipped_entries) == {
        "31; 0 0 COMMENT - SCHEMA x_extension shared_admin",
        "32; 0 0 ACL x_extension TABLE spatial_ref_sys shared_admin",
        "33; 0 1 SEQUENCE SET x_extension topology_id_seq shared_admin",
    }


def test_composes_with_a_partial_restore_use_list() -> None:
    """A T-243 use-list already has ';'-commented corrupted entries; they stay as they are."""
    lines = [
        ";4368; 0 21170 TABLE DATA public geo_cache kor_travel_geo_app",
        "2; 3079 19716 EXTENSION - postgis ",
        "252; 1259 21170 TABLE public geo_cache kor_travel_geo_app",
    ]

    result = filter_preprovisioned_toc(lines, extensions=("postgis",), schemas=())

    assert result.lines == (
        ";4368; 0 21170 TABLE DATA public geo_cache kor_travel_geo_app",
        ";2; 3079 19716 EXTENSION - postgis ",
        "252; 1259 21170 TABLE public geo_cache kor_travel_geo_app",
    )
    assert result.skipped_entries == ("2; 3079 19716 EXTENSION - postgis",)
