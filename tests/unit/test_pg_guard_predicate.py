"""The database guard that gates every opt-in PostgreSQL test (issue #523).

This runs offline and is the reason the guard can be trusted. Three properties are pinned, and
each one has been broken in practice:

1. the predicate refuses real databases — the copy this replaces used
   ``startswith("kor_travel_geo")``, which matched **production**, and the first version of the
   consolidated predicate allowed any ``t<NNN>`` segment, which matched the T-213 preserved
   baseline;
2. every write-heavy module actually *calls* the guard — asserting the bare name passed while the
   call was deleted, because the ``import`` line satisfied it;
3. the call happens *before* the first write — moving the guard after ``_apply_schema_idempotent``
   left the whole suite green.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.integration._pg_guard import (
    ALLOW_ENV,
    is_disposable_test_database,
    is_protected_database,
)

_TESTS_DIR = Path(__file__).resolve().parents[1]
_INTEGRATION_DIR = _TESTS_DIR / "integration"

_GUARD_CALL = "require_disposable_database"

#: Source markers for "this statement writes to the database it is connected to", matched in the
#: TEST module's own source. `CREATE EXTENSION IF NOT EXISTS` is deliberately excluded: it is
#: idempotent and several suites issue it against a loaded database on purpose.
#: KNOWN GAP: the C11-C17 suites create and drop staging tables through helpers in `src/`
#: (`recreate_shape_staging_table`), so their DDL is invisible here and they are NOT in the
#: derived list. They are not read-only — guarding them is deferred, see issue #525.
#: Case-SENSITIVE on purpose: matching `truncate` case-insensitively also matches Python
#: identifiers like `truncated_archive`, which flagged a module that only writes through an
#: already-guarded helper.
_WRITE_AWAIT = re.compile(
    r"iter_sql_statements\(\s*(?:SCHEMA_SQL|INDEX_SQL|MV_SQL)|TRUNCATE\s|CREATE\s+TABLE"
    r"|DROP\s+TABLE|INSERT\s+INTO|CREATE\s+MATERIALIZED"
)


#: Looser than `_WRITE_AWAIT`, and used only to classify a FUNCTION as a writer. A function that
#: merely mentions SCHEMA_SQL/INDEX_SQL/MV_SQL applies them — `_apply_schema_idempotent` loops
#: `for sql_block in (SCHEMA_SQL, INDEX_SQL)`, so requiring the constant inside
#: `iter_sql_statements(...)` classified it as harmless and let a guard move after it.
_WRITER_BODY = re.compile(
    r"\b(?:SCHEMA_SQL|INDEX_SQL|MV_SQL)\b|TRUNCATE\s|CREATE\s+TABLE"
    r"|DROP\s+TABLE|INSERT\s+INTO|CREATE\s+MATERIALIZED"
)


def _calls(source: str, name: str) -> bool:
    """`name(` as a whole identifier — a bare substring test matches `make_async_engine(`."""
    return re.search(rf"(?<![\w.]){re.escape(name)}\s*\(", source) is not None


#: Modules that create their own databases and write only to those. `_hotswap_roundtrip.py` does
#: connect straight to the databases it made (it INSERTs a marker row), so the exemption is about
#: OWNERSHIP, not about connecting via `postgres`: their names are minted at runtime and carry an
#: `e2e` segment so the guard inside `build_minimal_serving_schema` still accepts them.
_MANAGES_OWN_DATABASES = frozenset(
    {"_hotswap_roundtrip.py", "test_scratch_db_roundtrip.py", "_pg_guard.py"}
)
#: Guarded by a STRICTER mechanism: `validate_t177_confirmation` demands a typed
#: `RUN-T177-E2E <database>` confirmation on top of the name predicate, which it now shares.
_STRICTER_OWN_GATE = frozenset({"_t177_full_load_harness.py"})


def _integration_modules() -> list[Path]:
    return sorted(p for p in _INTEGRATION_DIR.glob("*.py") if p.name != "__init__.py")


def _writes_to_the_dsn_database(source: str) -> bool:
    return "KTG_TEST_PG_DSN" in source and bool(_WRITE_AWAIT.search(source))


def _modules_requiring_a_guard() -> list[Path]:
    """Derived, not hardcoded — a hardcoded list is how two modules ended up unguarded."""
    return [
        path
        for path in _integration_modules()
        if path.name not in _MANAGES_OWN_DATABASES
        and path.name not in _STRICTER_OWN_GATE
        and _writes_to_the_dsn_database(path.read_text(encoding="utf-8"))
    ]


@pytest.mark.parametrize(
    "name",
    [
        "kor_travel_geo",  # production — the exact name the original predicate let through
        "KOR_TRAVEL_GEO",
        " kor_travel_geo ",
        "kor_travel_geo_dagster",
        # T-213 preserved baselines: docs/t213-data-preservation.md mandates this shape, and the
        # database holds an active serving release plus 6.4M-row MVs. The first version of this
        # predicate allowed it via a `t\\d{2,4}` segment rule.
        "kor_travel_geo_t213",
        "kor_travel_geo_t213_20260615_r3",
        "kor_travel_geo_restore",  # ADR-036 hot-swap target, renamed into production
        "postgres",
        "template1",
        "",
        "geocoder",
        "kor_travel_geo_prod",
        # ADR-036 rollback alias — a COPY OF PRODUCTION kept for the retention window.
        "kor_travel_geo_previous_20260529_010203",
    ],
)
def test_real_databases_are_refused(name: str) -> None:
    assert is_disposable_test_database(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "kor_travel_geo_test",
        "kor_travel_geo_rt",  # documented DSN in test_backup_restore_roundtrip.py
        "kor_travel_geo_fullload_e2e",  # docs/deploy/staging-full-load.md
        "ktg_probe_test",
        "tmp_probe",
        "scratch",
        "geo-test-01",
        # Minted at runtime by the T-246 hot-swap harness. The `e2e` segment is load-bearing:
        # without it the guard skipped all three live hot-swap/rollback tests, and the name
        # cannot be pre-declared in KTG_TEST_PG_ALLOW_WRITES because it does not exist until
        # the harness runs.
        "ktg_t246_cur_e2e_deadbeef",
        "ktg_t246_prev_e2e_deadbeef",
    ],
)
def test_scratch_databases_are_allowed(name: str) -> None:
    assert is_disposable_test_database(name) is True


def test_none_is_refused() -> None:
    assert is_disposable_test_database(None) is False


def test_task_tags_alone_do_not_imply_disposable() -> None:
    """A task tag says which task owns the database, not that it may be destroyed."""
    assert is_disposable_test_database("kor_travel_geo_t177") is False
    assert is_disposable_test_database("kor_travel_geo_t046_daegu") is False
    # ...but a task tag alongside a real throwaway marker is fine.
    assert is_disposable_test_database("kor_travel_geo_t177_scratch") is True


def test_explicit_opt_in_allows_an_unusual_name() -> None:
    """The escape hatch for ad-hoc review databases this repo actually uses."""
    name = "kor_travel_geo_codex_pr12_review"
    assert is_disposable_test_database(name) is False
    assert is_disposable_test_database(name, env={ALLOW_ENV: name}) is True
    # Must match the actual database, not merely be set.
    assert is_disposable_test_database(name, env={ALLOW_ENV: "something_else"}) is False


@pytest.mark.parametrize(
    "name",
    [
        "kor_travel_geo",
        "kor_travel_geo_t213_20260615_r3",
        "kor_travel_geo_restore",
        "kor_travel_geo_previous_20260529_010203",
    ],
)
def test_opt_in_never_overrides_a_protected_database(name: str) -> None:
    assert is_protected_database(name) is True
    assert is_disposable_test_database(name, env={ALLOW_ENV: name}) is False


def test_every_write_heavy_module_is_guarded() -> None:
    """Every module must call the guard ITSELF.

    An earlier version also accepted "calls a helper that is guarded", resolved from a
    repo-global pool of guarded function names. That pool contained `engine` (a module-scoped
    fixture), and the call-matcher matched the *definition* line `async def engine(` — so merely
    naming a fixture `engine` gave a brand-new unguarded module a free pass. Verified: a module
    doing `TRUNCATE load_jobs CASCADE` with no guard passed until its fixture was renamed.
    Every module that currently needs a guard calls it directly, so the branch bought nothing.
    """
    unguarded = [
        path.name
        for path in _modules_requiring_a_guard()
        if f"await {_GUARD_CALL}(" not in path.read_text(encoding="utf-8")
    ]
    assert unguarded == [], f"modules write to {'KTG_TEST_PG_DSN'} without the guard: {unguarded}"


def test_the_derivation_actually_finds_the_known_writers() -> None:
    """Guards the guard: if the marker regex stops matching, the test above passes vacuously."""
    found = {path.name for path in _modules_requiring_a_guard()}
    for expected in (
        "test_t210_source_integration.py",
        "test_full_load_batch_dagster_roundtrip.py",
        "test_optional_real_postgres_load.py",
        "_backup_roundtrip.py",
    ):
        assert expected in found, f"{expected} no longer detected as a writer"


def _writer_functions(tree: ast.AST, source: str) -> set[str]:
    """Async functions in this module whose own body writes to the database.

    Needed because the write is usually one level down: `await _apply_schema_idempotent(eng)`
    contains no SQL of its own, and treating it as harmless is exactly how a guard moved after
    it goes unnoticed.
    """
    writers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and _WRITER_BODY.search(
            ast.get_source_segment(source, node) or ""
        ):
            writers.add(node.name)
    return writers


def _guard_precedes_first_write(source: str) -> tuple[bool, str]:
    """True if, in every function that calls the guard, no write happens before it.

    Line-based within the function rather than per-`Await`, because the dominant idiom here is

        for sql in iter_sql_statements(SCHEMA_SQL):
            await conn.execute(text(sql))

    where the awaited expression is just `conn.execute(text(sql))` and carries no marker at all —
    the write is named on the `for` line. An earlier version inspected only `Await` source
    segments and therefore could not see the exact shape it was written to protect: moving the
    guard below that loop left the suite green.
    """
    tree = ast.parse(source)
    writers = _writer_functions(tree, source)
    lines = source.splitlines()
    for func in ast.walk(tree):
        if not isinstance(func, ast.AsyncFunctionDef):
            continue
        end = func.end_lineno or func.lineno
        guard_line = next(
            (
                n
                for n in range(func.lineno, end + 1)
                if f"await {_GUARD_CALL}(" in lines[n - 1]
            ),
            None,
        )
        if guard_line is None:
            continue
        for n in range(func.lineno + 1, guard_line):
            line = lines[n - 1]
            if line.lstrip().startswith("#"):
                continue
            hits_writer = any(_calls(line, name) for name in writers if name != func.name)
            if _WRITER_BODY.search(line) or hits_writer:
                return False, f"{func.name}: write at line {n} precedes the guard at {guard_line}"
    return True, ""


@pytest.mark.parametrize("path", _modules_requiring_a_guard(), ids=lambda p: p.name)
def test_guard_runs_before_the_first_write(path: Path) -> None:
    """A guard that runs after the first write is not a guard.

    Verified to fail: moving the call in `test_t210_source_integration.py` to after
    `_apply_schema_idempotent` left every other assertion in this file green.
    """
    ok, why = _guard_precedes_first_write(path.read_text(encoding="utf-8"))
    assert ok, f"{path.name}: {why}"


def test_no_second_definition_of_a_disposability_predicate() -> None:
    """Four copies had drifted and one matched production. There must be exactly one.

    Matched by shape rather than by the old name: the fourth copy was called
    `looks_like_t177_scratch_database`, so a name-based scan could not see it.
    """
    pattern = re.compile(
        r"^\s*def (?!test_)\w*(?:disposable|scratch|throwaway)\w*\([^)]*\)\s*->\s*bool:",
        re.MULTILINE,
    )
    offenders: list[str] = []
    for path in _TESTS_DIR.rglob("*.py"):
        if path.name in {"_pg_guard.py", Path(__file__).name}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line = text[match.start() : text.index("\n", match.start())].strip()
            # A thin delegation to the shared predicate is fine; a second implementation is not.
            body_start = text.index("\n", match.start())
            body = text[body_start : body_start + 1200]
            if "is_disposable_test_database(" in body:
                continue
            offenders.append(f"{path.relative_to(_TESTS_DIR)}: {line}")
    assert offenders == [], f"second disposability predicate(s) found: {offenders}"
