from __future__ import annotations

import io
import zipfile

from kraddr.geo import iter_legal_dong_records
from kraddr.geo.legal_dong import records_from_openapi_rows

LEGAL_DONG_CSV = "\n".join(
    [
        "법정동코드,법정동명,폐지여부",
        "1100000000,서울특별시,존재",
        "2671031000,부산광역시 기장군 일광면,폐지",
    ]
)


def test_iter_legal_dong_records_from_cp949_csv() -> None:
    records = list(iter_legal_dong_records(LEGAL_DONG_CSV.encode("cp949")))

    assert records[0].legal_dong_code == "1100000000"
    assert records[0].legal_dong_level == "sido"
    assert records[0].is_active is True
    assert records[1].is_active is False
    assert records[1].sigungu_code == "26710"


def test_iter_legal_dong_records_from_zip() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("legal.csv", LEGAL_DONG_CSV.encode("cp949"))

    records = list(iter_legal_dong_records(buffer.getvalue()))

    assert len(records) == 2
    assert records[0].legal_dong_name == "서울특별시"


def test_records_from_openapi_rows_constructs_full_name() -> None:
    records = list(
        records_from_openapi_rows(
            [
                {
                    "법정동코드": "1111010100",
                    "시도명": "서울특별시",
                    "시군구명": "종로구",
                    "읍면동명": "청운동",
                    "폐지여부": "존재",
                }
            ]
        )
    )

    assert records[0].legal_dong_name == "서울특별시 종로구 청운동"
    assert records[0].eup_myeon_dong_code == "11110101"
