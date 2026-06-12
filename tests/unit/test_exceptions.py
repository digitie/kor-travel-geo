from kortravelgeo.exceptions import InvalidAddressError, KorTravelGeoError


def test_domain_errors_share_kor_travel_geo_base() -> None:
    error = InvalidAddressError("bad address", hint="주소 형식을 확인하세요.")

    assert isinstance(error, KorTravelGeoError)
    assert error.code == "E0101"
    assert error.http_status == 400
    assert error.hint == "주소 형식을 확인하세요."
