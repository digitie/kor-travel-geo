from kraddr.geo.exceptions import InvalidAddressError, KraddrGeoError


def test_domain_errors_share_kraddr_geo_base() -> None:
    error = InvalidAddressError("bad address", hint="주소 형식을 확인하세요.")

    assert isinstance(error, KraddrGeoError)
    assert error.code == "E0101"
    assert error.http_status == 400
    assert error.hint == "주소 형식을 확인하세요."
