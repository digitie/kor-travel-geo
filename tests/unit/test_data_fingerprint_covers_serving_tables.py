"""The data fingerprint hashes exactly the tables the v2 responses are built from (ADR-069 D2).

The table set is derived, not chosen: every ``FROM``/``JOIN`` target in the five v2 infra repos'
source, minus CTE names and function calls, minus the reasoned allow-list, must equal
``DATA_FINGERPRINT_TABLES`` — both directions. A repo that starts reading a new table, a table
dropped from the set, or a stale allow-list entry turns this red.

Matching is case-sensitive on purpose: SQL keywords in these modules are upper case, and that is
the only thing that keeps Python's ``from __future__``/``from kortravelgeo`` out of the set. A
lower-case ``from tl_x`` in SQL is invisible to this lint — keep SQL keywords upper case.
"""

from __future__ import annotations

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
V2_REPO_MODULES = ("reverse_repo", "zip_repo", "geometry_repo", "geocode_repo", "search_repo")

_FROM_JOIN_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)(\s*\()?")
_CTE_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s+AS\s+(?:(?:NOT\s+)?MATERIALIZED\s+)?\(")


def derive_serving_tables(sources: list[str]) -> set[str]:
    """FROM/JOIN identifiers minus CTE names and function calls (ADR-069 D2 steps 1-2)."""
    referenced: set[str] = set()
    ctes: set[str] = set()
    for source in sources:
        for match in _FROM_JOIN_RE.finditer(source):
            if match.group(2) is None:  # `JOIN generate_series(...)` is a call, not a table
                referenced.add(match.group(1))
        ctes.update(_CTE_RE.findall(source))
    return referenced - ctes


def _repo_sources() -> list[str]:
    return [(_INFRA / f"{name}.py").read_text(encoding="utf-8") for name in V2_REPO_MODULES]


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
    assert_fingerprint_covers(derive_serving_tables(_repo_sources()))


def test_fingerprint_table_specs_are_unique_and_named() -> None:
    names = [spec.name for spec in DATA_FINGERPRINT_TABLE_SPECS]
    assert len(names) == len(set(names)) == len(DATA_FINGERPRINT_TABLES) == 11


def test_allowlist_entries_carry_a_reason() -> None:
    assert DATA_FINGERPRINT_ALLOWLIST
    assert all(reason.strip() for reason in DATA_FINGERPRINT_ALLOWLIST.values())


# --- the lint must actually discriminate (ADR-069 T-325a acceptance (5)) ---------------------


def test_lint_goes_red_when_a_repo_starts_reading_a_new_table() -> None:
    fake = 'SQL = """SELECT 1 FROM mv_geocode_target t JOIN tl_new_table n"""'
    sources = [*_repo_sources(), fake]
    with pytest.raises(AssertionError, match="tl_new_table"):
        assert_fingerprint_covers(derive_serving_tables(sources))


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
        globals(), "DATA_FINGERPRINT_TABLES", DATA_FINGERPRINT_TABLES - {"tl_kodis_bas"}
    )
    with pytest.raises(AssertionError, match="tl_kodis_bas"):
        assert_fingerprint_covers(derive_serving_tables(_repo_sources()))


@pytest.mark.parametrize(
    "extra_sql",
    [
        "WITH fresh_cte AS (SELECT 1) SELECT * FROM fresh_cte",
        "WITH fresh_cte AS MATERIALIZED (SELECT 1) SELECT * FROM fresh_cte",
        "WITH fresh_cte AS NOT MATERIALIZED (SELECT 1) SELECT * FROM fresh_cte",
        "SELECT * FROM mv_geocode_target t JOIN generate_series(1, 3) g ON true",
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
