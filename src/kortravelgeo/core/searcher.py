"""Search orchestration."""

from __future__ import annotations

from kortravelgeo.dto.region import RegionHint
from kortravelgeo.dto.search import SearchInput, SearchResponse, SearchResultItem

from .protocols import SearchRepo
from .responses import service_meta, structure_from_lookup


async def search(
    repo: SearchRepo,
    inp: SearchInput,
    *,
    region_hint: RegionHint | None = None,
) -> SearchResponse:
    rows, total = await repo.search(
        inp.query,
        search_type=inp.type,
        page=inp.page,
        size=inp.size,
        region_hint=region_hint,
    )
    items = tuple(
        SearchResultItem(
            type=row.type,
            title=row.title,
            address=row.address,
            structure=structure_from_lookup(row.lookup) if row.lookup else None,
            point=row.lookup.point if row.lookup else None,
            source="local",
            score=row.score,
        )
        for row in rows
    )
    return SearchResponse(
        service=service_meta("search"),
        status="OK" if items else "NOT_FOUND",
        input=inp,
        result=items,
        total=total,
    )
