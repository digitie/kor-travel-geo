"""Delta merge helpers for SHP auxiliary tables."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.settings import LoadCodeAction

PK_MAP: dict[str, tuple[str, ...]] = {
    "tl_scco_ctprvn": ("ctprvn_cd",),
    "tl_scco_sig": ("sig_cd",),
    "tl_scco_emd": ("emd_cd",),
    "tl_scco_li": ("li_cd",),
    "tl_kodis_bas": ("bas_mgt_sn",),
    "tl_spbd_buld_polygon": ("bd_mgt_sn",),
    "tl_sprd_manage": ("sig_cd", "rds_man_no"),
    "tl_sprd_intrvl": ("sig_cd", "rds_man_no", "bsi_int_sn"),
    "tl_sprd_rw": ("sig_cd", "rw_sn"),
}


async def apply_delta(
    engine: AsyncEngine,
    *,
    table_name: str,
    staging_table: str,
    code_actions: Mapping[str, LoadCodeAction],
    mvm_res_cd_column: str = "mvm_res_cd",
) -> None:
    pk = PK_MAP[table_name]
    insert_codes = tuple(
        code for code, action in code_actions.items() if action in {"insert", "update"}
    )
    delete_codes = tuple(code for code, action in code_actions.items() if action == "delete")
    join_predicate = " AND ".join(f"t.{col} = s.{col}" for col in pk)
    columns_sql = await _columns(engine, table_name)
    update_assignments = ", ".join(
        f"{col} = EXCLUDED.{col}" for col in columns_sql if col not in pk
    )
    async with engine.begin() as conn:
        if insert_codes:
            await conn.execute(
                text(
                    f"""
INSERT INTO {table_name} ({", ".join(columns_sql)})
SELECT {", ".join(columns_sql)}
  FROM {staging_table}
 WHERE {mvm_res_cd_column} = ANY(:codes)
ON CONFLICT ({", ".join(pk)}) DO UPDATE SET {update_assignments}
"""
                ),
                {"codes": list(insert_codes)},
            )
        if delete_codes:
            await conn.execute(
                text(
                    f"""
DELETE FROM {table_name} t
 USING {staging_table} s
 WHERE {join_predicate}
   AND s.{mvm_res_cd_column} = ANY(:codes)
"""
                ),
                {"codes": list(delete_codes)},
            )


async def _columns(engine: AsyncEngine, table_name: str) -> tuple[str, ...]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
SELECT column_name
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name = :table_name
   AND is_generated = 'NEVER'
   AND column_name <> 'loaded_at'
 ORDER BY ordinal_position
"""
                ),
                {"table_name": table_name},
            )
        ).scalars().all()
    return tuple(rows)
