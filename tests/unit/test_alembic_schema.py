import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION_PATH = REPO_ROOT / "alembic/versions/0001_initial_postgis_schema.py"


def _revision_tree() -> ast.Module:
    return ast.parse(REVISION_PATH.read_text(encoding="utf-8"))


def test_initial_revision_references_all_schema_sql_files_in_order() -> None:
    namespace: dict[str, object] = {}
    tree = _revision_tree()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue

        if value is None:
            continue

        for target in targets:
            if isinstance(target, ast.Name) and target.id in {
                "revision",
                "down_revision",
                "SQL_FILES",
            }:
                namespace[target.id] = ast.literal_eval(value)

    assert namespace["revision"] == "0001_initial_postgis_schema"
    assert namespace["down_revision"] is None
    assert namespace["SQL_FILES"] == (
        "sql/ddl/001_extensions.sql",
        "sql/ddl/010_master_tables.sql",
        "sql/ddl/020_auxiliary_tables.sql",
        "sql/ddl/030_meta_tables.sql",
        "sql/indexes.sql",
        "sql/mv.sql",
    )

    for relative_path in namespace["SQL_FILES"]:
        assert (REPO_ROOT / relative_path).is_file()


def test_initial_revision_downgrade_drops_mv_before_tables() -> None:
    source = REVISION_PATH.read_text(encoding="utf-8")

    mv_pos = source.index("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target")
    first_table_pos = source.index('"geo_cache"')

    assert mv_pos < first_table_pos
    assert "tl_spbd_entrc" in source
    assert "tl_scco_ctprvn" in source
