"""The data fingerprint hashes exactly the tables the v2 responses are built from (ADR-069 D2).

The table set is derived, not chosen. Every ``infra/*_repo.py`` module is scanned unless it is on
``NON_V2_REPO_MODULES`` (each with a reason, and each checked to be unused by the v2 client
methods), so a new repo cannot hide. Per module, the ``FROM``/``JOIN`` targets (comma joins,
``ONLY``, ``LATERAL`` and schema-qualified names included) minus that module's own CTE names and
function calls, unioned over modules, minus the reasoned allow-list, must equal
``DATA_FINGERPRINT_TABLES`` — both directions.

Matching is case-sensitive on purpose: SQL keywords in these modules are upper case, and that is
the only thing that keeps Python's ``from __future__``/``from kortravelgeo`` out of the set. A
lower-case ``from tl_x`` in SQL is invisible to this lint — keep SQL keywords upper case.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import pytest

from kortravelgeo.infra.data_fingerprint import (
    DATA_FINGERPRINT_ALLOWLIST,
    DATA_FINGERPRINT_TABLE_SPECS,
    DATA_FINGERPRINT_TABLES,
)

_INFRA = Path(__file__).resolve().parents[2] / "src" / "kortravelgeo" / "infra"

#: Repo modules no v2 lookup reads, with the reason; everything else under infra/*_repo.py is
#: scanned. The class names are checked against the v2 client methods below.
NON_V2_REPO_MODULES: dict[str, tuple[str, str]] = {
    "admin_repo": ("AdminRepository", "ops ledger/admin surfaces; v2 reads only the release id"),
    "file_inventory_repo": ("FileInventoryRepository", "admin source-file inventory"),
    "source_upload_repo": ("SourceUploadSessionRepository", "admin source-file uploads"),
    "pobox_repo": ("PoboxRepository", "v1 /v1/address/pobox only"),
    "zip_repo": ("ZipRepository", "v1 /v1/address/zipcode only (v2 zip comes from the MV)"),
}

#: AsyncAddressClient methods that build the four v2 lookup answers.
V2_CLIENT_METHODS = (
    "geocode",
    "_geocode_v2",
    "_geocode_v1",
    "_geocode_supplemental_road_candidates",
    "_geocode_road_or_region_candidates",
    "_with_geocode_geometries",
    "_enrich_candidates_with_geometry",
    "reverse",
    "_reverse_geocode_v1",
    "search",
    "_search_v1",
    "regions_within_radius",
)

_IDENT = r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?"
_FROM_CLAUSE_RE = re.compile(
    r"\bFROM\s+(.*?)(?=\b(?:WHERE|JOIN|LEFT|RIGHT|INNER|CROSS|FULL|NATURAL|ON|USING|GROUP|ORDER"
    r"|LIMIT|OFFSET|UNION|EXCEPT|INTERSECT|HAVING|WINDOW|RETURNING|FOR)\b|\)|;|\"\"\"|$)",
    re.S,
)
_FROM_ITEM_RE = re.compile(rf"\s*(?:LATERAL\s+)?(?:ONLY\s+)?({_IDENT})(\s*\()?")
_JOIN_RE = re.compile(rf"\bJOIN\s+(?:LATERAL\s+)?(?:ONLY\s+)?({_IDENT})(\s*\()?")
_CTE_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s+AS\s+(?:(?:NOT\s+)?MATERIALIZED\s+)?\(")


def _normalize(name: str) -> str:
    return name.removeprefix("public.")


def module_tables(source: str) -> set[str]:
    """One module's FROM/JOIN relations minus its own CTEs and function calls."""
    referenced: set[str] = set()
    for clause in _FROM_CLAUSE_RE.finditer(source):
        for item in clause.group(1).split(","):
            match = _FROM_ITEM_RE.match(item)
            if match and match.group(2) is None:
                referenced.add(_normalize(match.group(1)))
    for match in _JOIN_RE.finditer(source):
        if match.group(2) is None:  # `JOIN generate_series(...)` is a call, not a table
            referenced.add(_normalize(match.group(1)))
    return referenced - set(_CTE_RE.findall(source))


def derive_serving_tables(sources: list[str]) -> set[str]:
    """Union over modules — a CTE name in one module never hides a table in another."""
    derived: set[str] = set()
    for source in sources:
        derived |= module_tables(source)
    return derived


def v2_repo_modules() -> list[str]:
    names = sorted(path.stem for path in _INFRA.glob("*_repo.py"))
    return [name for name in names if name not in NON_V2_REPO_MODULES]


def _repo_sources() -> list[str]:
    return [(_INFRA / f"{name}.py").read_text(encoding="utf-8") for name in v2_repo_modules()]


def assert_fingerprint_covers(derived: set[str]) -> None:
    allowlist = set(DATA_FINGERPRINT_ALLOWLIST)
    phantom = allowlist - derived
    assert not phantom, f"allow-list entries no v2 repo reads: {sorted(phantom)}"
    expected = derived - allowlist
    assert expected, "derived serving-table set is empty — the derivation itself is broken"
    missing = expected - DATA_FINGERPRINT_TABLES
    extra = DATA_FINGERPRINT_TABLES - expected
    assert not missing, f"v2 repos read tables the fingerprint does not hash: {sorted(missing)}"
    assert not extra, f"fingerprint hashes tables no v2 repo reads: {sorted(extra)}"


def test_fingerprint_tables_equal_v2_repo_from_join_set() -> None:
    expected_v2 = {"geocode_repo", "geometry_repo", "reverse_repo", "search_repo"}
    assert set(v2_repo_modules()) >= expected_v2
    assert_fingerprint_covers(derive_serving_tables(_repo_sources()))


def test_non_v2_repo_allowlist_is_real_and_unused_by_v2_methods() -> None:
    from kortravelgeo.client import AsyncAddressClient

    present = {path.stem for path in _INFRA.glob("*_repo.py")}
    assert set(NON_V2_REPO_MODULES) <= present, "stale non-v2 repo entry"
    v2_source = "\n".join(
        inspect.getsource(getattr(AsyncAddressClient, name)) for name in V2_CLIENT_METHODS
    )
    for module, (class_name, reason) in NON_V2_REPO_MODULES.items():
        assert reason.strip()
        if module == "admin_repo":
            continue  # v2 reads the release stamp through dataset_ref(), not answer data
        assert class_name not in v2_source, f"{class_name} is used on a v2 path: scan {module}"


def test_fingerprint_table_specs_are_unique_and_named() -> None:
    names = [spec.name for spec in DATA_FINGERPRINT_TABLE_SPECS]
    assert len(names) == len(set(names)) == len(DATA_FINGERPRINT_TABLES) == 9


def test_allowlist_entries_carry_a_reason() -> None:
    assert DATA_FINGERPRINT_ALLOWLIST
    assert all(reason.strip() for reason in DATA_FINGERPRINT_ALLOWLIST.values())


def test_text_search_mv_reads_only_mv_geocode_target() -> None:
    """The allow-list reason for mv_geocode_text_search: it is a projection of
    mv_geocode_target (same REFRESH), so hashing the target covers it."""
    from kortravelgeo.infra.sql import TEXT_SEARCH_MV_SQL

    start = TEXT_SEARCH_MV_SQL.index("CREATE MATERIALIZED VIEW mv_geocode_text_search")
    definition = TEXT_SEARCH_MV_SQL[start : TEXT_SEARCH_MV_SQL.index("WITH DATA", start)]
    assert module_tables(definition) == {"mv_geocode_target"}


# --- the lint must actually discriminate (ADR-069 T-325a acceptance (5)) ---------------------


@pytest.mark.parametrize(
    "fake",
    [
        "SELECT 1 FROM mv_geocode_target t JOIN tl_new_table n ON true",
        "SELECT 1 FROM mv_geocode_target t, tl_new_table n",
        "SELECT 1 FROM ONLY tl_new_table",
        "SELECT 1 FROM public.tl_new_table",
        "SELECT 1 FROM mv_geocode_target t JOIN LATERAL tl_new_table n ON true",
    ],
)
def test_lint_goes_red_when_a_repo_starts_reading_a_new_table(fake: str) -> None:
    sources = [*_repo_sources(), f'SQL = """{fake}"""']
    with pytest.raises(AssertionError, match="tl_new_table"):
        assert_fingerprint_covers(derive_serving_tables(sources))


def test_lint_goes_red_for_another_schema() -> None:
    sources = [*_repo_sources(), 'SQL = """SELECT 1 FROM ops.serving_releases"""']
    with pytest.raises(AssertionError, match=r"ops\.serving_releases"):
        assert_fingerprint_covers(derive_serving_tables(sources))


def test_cte_name_in_one_module_does_not_hide_a_table_in_another() -> None:
    sources = [
        *_repo_sources(),
        'A = """WITH tl_new_table AS (SELECT 1) SELECT * FROM tl_new_table"""',
        'B = """SELECT * FROM tl_new_table"""',
    ]
    with pytest.raises(AssertionError, match="tl_new_table"):
        assert_fingerprint_covers(derive_serving_tables(sources))


def test_lint_goes_red_when_a_new_repo_module_reads_a_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for path in _INFRA.glob("*_repo.py"):
        (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "poi_repo.py").write_text('SQL = """SELECT 1 FROM tl_poi"""', encoding="utf-8")
    monkeypatch.setitem(globals(), "_INFRA", tmp_path)
    with pytest.raises(AssertionError, match="tl_poi"):
        assert_fingerprint_covers(derive_serving_tables(_repo_sources()))


def test_lint_goes_red_on_a_phantom_allowlist_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        globals(),
        "DATA_FINGERPRINT_ALLOWLIST",
        {**DATA_FINGERPRINT_ALLOWLIST, "tl_never_read": "phantom"},
    )
    with pytest.raises(AssertionError, match="tl_never_read"):
        assert_fingerprint_covers(derive_serving_tables(_repo_sources()))


def test_lint_goes_red_when_a_table_is_dropped_from_the_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        globals(), "DATA_FINGERPRINT_TABLES", DATA_FINGERPRINT_TABLES - {"tl_sppn_makarea"}
    )
    with pytest.raises(AssertionError, match="tl_sppn_makarea"):
        assert_fingerprint_covers(derive_serving_tables(_repo_sources()))


@pytest.mark.parametrize(
    "extra_sql",
    [
        "WITH fresh_cte AS (SELECT 1) SELECT * FROM fresh_cte",
        "WITH fresh_cte AS MATERIALIZED (SELECT 1) SELECT * FROM fresh_cte",
        "WITH fresh_cte AS NOT MATERIALIZED (SELECT 1) SELECT * FROM fresh_cte",
        "SELECT * FROM mv_geocode_target t JOIN generate_series(1, 3) g ON true",
        "SELECT * FROM generate_series(1, 3) g, mv_geocode_target t",
        "SELECT * FROM (SELECT 1) s",
    ],
)
def test_lint_stays_green_for_ctes_and_function_calls(extra_sql: str) -> None:
    sources = [*_repo_sources(), f'SQL = """{extra_sql}"""']
    assert_fingerprint_covers(derive_serving_tables(sources))


# --- column lists (ADR-069 D1 lever 1: explicit columns, so the lint pins them too) ----------

_COLUMN_LINE_RE = re.compile(r"^  ([a-z_][a-z0-9_]*)\s+[A-Za-z]")
_CONSTRAINT_WORDS = {"primary", "check", "constraint", "unique", "foreign", "exclude"}


def ddl_columns(schema_sql: str, table: str) -> set[str]:
    """Column names of ``CREATE TABLE IF NOT EXISTS <table> (...)`` in the fresh-init DDL."""
    start = schema_sql.index(f"CREATE TABLE IF NOT EXISTS {table} (")
    body = schema_sql[start : schema_sql.index("\n);", start)]
    columns = set()
    for line in body.splitlines()[1:]:
        match = _COLUMN_LINE_RE.match(line)
        if match and match.group(1) not in _CONSTRAINT_WORDS:
            columns.add(match.group(1))
    return columns


def mv_columns(mv_sql: str) -> set[str]:
    """Output columns of the ``mv_geocode_target`` SELECT list (2-space indented items)."""
    create_at = mv_sql.index("CREATE MATERIALIZED VIEW mv_geocode_target")
    select_at = mv_sql.index("\nSELECT\n", create_at)
    body = mv_sql[select_at + len("\nSELECT\n") : mv_sql.index("\nFROM tl_juso_text j")]
    columns = set()
    for line in body.splitlines():
        if not line.startswith("  ") or line.startswith("   ") or line.strip() == "CASE":
            continue
        item = line.strip().rstrip(",")
        alias = item.rsplit(" AS ", 1)[1] if " AS " in item else item.rsplit(".", 1)[-1]
        columns.add(alias)
    return columns


def _actual_columns(table: str) -> set[str]:
    from kortravelgeo.infra.sql import MV_SQL, SCHEMA_SQL

    return mv_columns(MV_SQL) if table == "mv_geocode_target" else ddl_columns(SCHEMA_SQL, table)


@pytest.mark.parametrize("spec", DATA_FINGERPRINT_TABLE_SPECS, ids=lambda spec: spec.name)
def test_fingerprint_column_lists_match_the_table_columns(spec: Any) -> None:
    from kortravelgeo.infra.data_fingerprint import EXCLUDED_COLUMNS

    actual = _actual_columns(spec.name)
    assert len(actual) >= 3, f"{spec.name}: column parse found {sorted(actual)}"
    expected = actual - EXCLUDED_COLUMNS
    assert spec.accounted_columns == expected, (
        f"{spec.name}: unaccounted {sorted(expected - spec.accounted_columns)}, "
        f"unknown {sorted(spec.accounted_columns - expected)}"
    )
    assert not (spec.accounted_columns & EXCLUDED_COLUMNS)


def test_column_lint_goes_red_on_a_new_column() -> None:
    from kortravelgeo.infra.sql import SCHEMA_SQL

    widened = SCHEMA_SQL.replace(
        "  bas_id          TEXT,\n", "  bas_id          TEXT,\n  bas_new_col     TEXT,\n", 1
    )
    assert "bas_new_col" in ddl_columns(widened, "tl_kodis_bas")
    assert "bas_new_col" not in ddl_columns(SCHEMA_SQL, "tl_kodis_bas")


def test_mv_column_parse_sees_case_and_alias_items() -> None:
    from kortravelgeo.infra.sql import MV_SQL

    parsed = mv_columns(MV_SQL)
    assert {"bd_mgt_sn", "si_nm", "sigungu_buld_nm", "pt_5179", "pt_4326", "pt_source"} <= parsed


def test_python_imports_are_not_mistaken_for_tables() -> None:
    derived = derive_serving_tables(_repo_sources())
    assert "__future__" not in derived
    assert "kortravelgeo" not in derived
    assert "sqlalchemy" not in derived
