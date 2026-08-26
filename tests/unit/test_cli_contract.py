from __future__ import annotations

import inspect
from pathlib import Path

from typer.testing import CliRunner

from kortravelgeo.cli.main import (
    _data_quality_cases,
    _load_bulk_with_cli_validation,
    _load_pobox_with_cli_validation,
    _shp_all_work_items,
    _shp_mode_for_index,
    app,
    load_all_sidos_command,
    load_bulk_command,
    load_daily_juso_command,
    load_daily_parcel_links_command,
    load_epost_command,
    load_parcel_links_command,
    load_pobox_command,
    load_roadaddr_entrances_command,
    load_shp_all_command,
    load_shp_command,
    load_sppn_makarea_command,
)


def test_cli_exposes_t018_operational_commands() -> None:
    runner = CliRunner()

    for command in (
        ["load", "--help"],
        ["load", "all-sidos", "--help"],
        ["load", "daily-juso", "--help"],
        ["load", "parcel-links", "--help"],
        ["load", "daily-parcel-links", "--help"],
        ["load", "roadaddr-entrances", "--help"],
        ["load", "shp-all", "--help"],
        ["load", "sppn-makarea", "--help"],
        ["load", "epost", "--help"],
        ["refresh", "mv", "--help"],
        ["validate", "consistency", "--help"],
        ["validate", "data-quality-samples", "--help"],
        ["backup", "create", "--help"],
        ["backup", "list", "--help"],
        ["backup", "show", "--help"],
        ["restore", "create", "--help"],
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output


def test_shp_all_full_mode_truncates_once_then_appends() -> None:
    assert _shp_mode_for_index("full", 0) == "full"
    assert _shp_mode_for_index("full", 1) == "append"
    assert _shp_mode_for_index("delta", 1) == "delta"


def test_shp_all_work_items_apply_full_mode_only_to_first_sido(tmp_path) -> None:
    first = tmp_path / "11"
    second = tmp_path / "26"
    first.mkdir()
    second.mkdir()

    items = _shp_all_work_items(tmp_path, "full")

    assert items == ((first, "full"), (second, "append"))


def test_multi_sido_shp_load_analyzes_only_after_last_sido() -> None:
    shp_all_source = inspect.getsource(load_shp_all_command)
    all_sidos_source = inspect.getsource(load_all_sidos_command)

    assert "items = _shp_all_work_items(root, mode)" in shp_all_source
    assert "analyze=index == len(items) - 1" in shp_all_source
    assert "sido_dirs = _sido_dirs(shp_root)" in all_sidos_source
    assert "analyze=index == len(sido_dirs) - 1" in all_sidos_source


def test_sppn_makarea_cli_load_exposes_source_yyyymm_and_mode() -> None:
    source = inspect.getsource(load_sppn_makarea_command)

    assert "load_sppn_makarea(" in source
    assert "--yyyymm" in source
    assert "--mode" in source
    assert 'typer.echo(f"loaded tl_sppn_makarea rows: {count}")' in source


def test_epost_cli_loads_through_shared_validation_helpers() -> None:
    assert "validate_pobox_file(path)" in inspect.getsource(_load_pobox_with_cli_validation)
    assert "validate_bulk_file(path)" in inspect.getsource(_load_bulk_with_cli_validation)
    assert "_load_pobox_with_cli_validation" in inspect.getsource(load_pobox_command)
    assert "_load_bulk_with_cli_validation" in inspect.getsource(load_bulk_command)
    assert "_load_pobox_with_cli_validation" in inspect.getsource(load_epost_command)
    assert "_load_bulk_with_cli_validation" in inspect.getsource(load_epost_command)


def test_direct_serving_and_all_sidos_cli_commands_record_serving_release() -> None:
    """T-291a: pobox/sppn_makarea/shp/bulk are served directly (no MV), and each of these CLI
    commands bypasses load_jobs entirely — each must record its own serving release on success
    rather than relying on a later, possibly-never-run `ktgctl refresh mv`."""

    for command in (
        load_shp_command,
        load_shp_all_command,
        load_sppn_makarea_command,
        load_pobox_command,
        load_bulk_command,
        load_epost_command,
        load_all_sidos_command,
    ):
        source = inspect.getsource(command)
        assert "record_mv_refresh_release" in source, command.__name__

    assert (
        'release_kind="daily_delta" if mode == "delta" else None'
        in inspect.getsource(load_shp_command)
    )
    assert (
        'release_kind="daily_delta" if mode == "delta" else None'
        in inspect.getsource(load_shp_all_command)
    )

    # all-sidos --no-refresh with no shp/pobox/bulk paths changes nothing servable (juso/
    # locsum/navi land in base tables the MV wasn't refreshed from) — recording unconditionally
    # there would be a false positive, the mirror image of the false negative T-291a exists to
    # fix. Must gate on refresh actually having happened, or a direct-serving path being loaded.
    all_sidos_source = inspect.getsource(load_all_sidos_command)
    assert "direct_serving_loaded = (" in all_sidos_source
    assert "shp_root is not None or pobox_path is not None or bulk_path is not None" in (
        all_sidos_source
    )
    assert "if refresh or direct_serving_loaded:" in all_sidos_source


def _indentation_scoped_if_body(source: str, condition: str) -> str:
    """The literal body text of ``if {condition}:``, delimited by indentation like Python
    actually scopes it — NOT by slicing between two substrings, which stays "inside" a block
    for any later code that merely appears before some other anchor text, even after being
    dedented back out of the if-block entirely."""
    lines = source.splitlines()
    header = f"if {condition}:"
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        indent = len(line) - len(line.lstrip(" "))
        body: list[str] = []
        for later in lines[index + 1 :]:
            if later.strip() == "":
                body.append(later)
                continue
            if len(later) - len(later.lstrip(" ")) <= indent:
                break
            body.append(later)
        return "\n".join(body)
    msg = f"no {header!r} block found"
    raise AssertionError(msg)


def test_daily_delta_cli_commands_can_refresh_and_label_daily_delta() -> None:
    """release_kind='daily_delta' sat in the enum with no producer before T-291a — the
    daily-juso/daily-parcel-links CLI commands are now the ones that can emit it.

    Checks the recording call is actually *inside* the ``if refresh:`` block by indentation,
    not merely present somewhere in the function before some later anchor text — a mutation
    that hoists ``record_mv_refresh_release`` back out to the enclosing scope (still textually
    before ``return result``) would record a spurious ``daily_delta`` release on every run,
    including the default ``--no-refresh`` path where no MV refresh happened at all.
    """

    for command in (load_daily_juso_command, load_daily_parcel_links_command):
        source = inspect.getsource(command)
        assert "--refresh/--no-refresh" in source
        if_refresh_block = _indentation_scoped_if_body(source, "refresh")
        assert "await refresh_mv(" in if_refresh_block
        assert "record_mv_refresh_release(" in if_refresh_block
        assert 'release_kind="daily_delta"' in if_refresh_block


def test_limit_per_file_commands_warn_test_only() -> None:
    for command in (
        load_daily_juso_command,
        load_parcel_links_command,
        load_daily_parcel_links_command,
        load_roadaddr_entrances_command,
    ):
        source = inspect.getsource(command)
        assert "_warn_limit_per_file(limit_per_file)" in source


def test_data_quality_case_parser_deduplicates_and_rejects_unknown() -> None:
    assert _data_quality_cases("c2,C4,c2") == ("C2", "C4")

    try:
        _data_quality_cases("C2,C99")
    except ValueError as exc:
        assert "unsupported data quality case(s): C99" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")


def test_data_quality_case_parser_rejects_empty_list() -> None:
    try:
        _data_quality_cases(" , ")
    except ValueError as exc:
        assert "at least one data quality case" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError")


def test_full_load_smoke_uses_v2_client_contract() -> None:
    script = Path("scripts/fullload_test.sh").read_text(encoding="utf-8")

    assert "r.candidates" in script
    assert "await client.reverse(" in script
    assert "reverse_geocode" not in script
    assert "r.result" not in script
