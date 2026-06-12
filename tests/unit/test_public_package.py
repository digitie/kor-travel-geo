from __future__ import annotations

import kortravelgeo as ktg


def test_public_root_import_exports_client_and_core_dtos() -> None:
    assert ktg.AsyncAddressClient.__name__ == "AsyncAddressClient"
    assert ktg.Point(x=127.0, y=37.5).x == 127.0
    assert ktg.ZipSource.BUILDING_BSI_ZON_NO == "building_bsi_zon_no"
    assert ktg.GeocodeV2Input(query="서울특별시 종로구 인사동").query == (
        "서울특별시 종로구 인사동"
    )
