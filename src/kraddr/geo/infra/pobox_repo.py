"""Raw SQL postal box repository."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import PoboxLookup

from ._rows import map_pobox

_POBOX_SQL = text(
    """
SELECT zip_no, pobox_kind, pobox_name, pobox_no_mn, pobox_no_sl,
       si_nm, sgg_nm, emd_nm, bjd_cd, count(*) OVER () AS total
  FROM postal_pobox
 WHERE (:kind = 'ALL' OR pobox_kind = :kind)
   AND (:si_nm IS NULL OR si_nm = :si_nm)
   AND (:sgg_nm IS NULL OR sgg_nm = :sgg_nm)
   AND (
     :query IS NULL
     OR pobox_name ILIKE '%' || :query || '%'
     OR zip_no = :query
     OR bjd_cd = :query
   )
 ORDER BY zip_no, pobox_kind, pobox_no_mn NULLS LAST
 LIMIT :limit OFFSET :offset
"""
)


class PoboxRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def lookup_poboxes(
        self,
        *,
        query: str | None,
        si_nm: str | None,
        sgg_nm: str | None,
        kind: Literal["PO", "PG", "ALL"],
        page: int,
        size: int,
    ) -> tuple[list[PoboxLookup], int]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    _POBOX_SQL,
                    {
                        "query": query,
                        "si_nm": si_nm,
                        "sgg_nm": sgg_nm,
                        "kind": kind,
                        "limit": size,
                        "offset": (page - 1) * size,
                    },
                )
            ).mappings().all()
        total = int(rows[0]["total"]) if rows else 0
        return ([map_pobox(dict(row)) for row in rows], total)
