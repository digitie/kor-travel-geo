from __future__ import annotations

from scripts.benchmark_api_latency import (
    ApiMeasurement,
    CorpusCase,
    Params,
    _fuzzy_address,
    _parcel_address,
    _road_address,
    build_api_cases,
    parse_server_profile,
    summarize,
)


def test_build_api_cases_maps_geocode_addresses() -> None:
    cases = build_api_cases(
        (
            CorpusCase(
                case_id="Q1-road-001",
                group="Q1_ROAD_EXACT",
                sql_name="road_exact",
                params={
                    "si": "서울특별시",
                    "sgg": "강남구",
                    "road_nrm": "테헤란로",
                    "mnnm": 152,
                    "slno": 3,
                    "buld_se_cd": "0",
                },
                label="서울특별시 강남구 테헤란로 152",
                source="mv_geocode_target",
            ),
            CorpusCase(
                case_id="Q2-parcel-001",
                group="Q2_PARCEL_EXACT",
                sql_name="parcel_exact",
                params={
                    "si": "강원특별자치도",
                    "sgg": "춘천시",
                    "emd": "신북읍",
                    "mntn_yn": "1",
                    "mnnm": 12,
                    "slno": 3,
                },
                label="강원특별자치도 춘천시 신북읍 산 12-3",
                source="mv_geocode_target",
            ),
            CorpusCase(
                case_id="Q3-fuzzy-sig-001",
                group="Q3_FUZZY_GEOCODE",
                sql_name="fuzzy_geocode_sig",
                params={
                    "si": None,
                    "sgg": None,
                    "road_nrm": "테헤란로",
                    "mnnm": 152,
                    "slno": 0,
                    "buld_se_cd": "0",
                    "sig_cd_filter": "11680",
                    "sig_cd_prefix": None,
                    "bjd_cd_filter": None,
                    "bjd_cd_prefix": None,
                    "limit": 5,
                },
                label="서울특별시 강남구 테헤란로 152",
                source="mv_geocode_target",
            ),
            CorpusCase(
                case_id="Q4-search-fuzzy-001",
                group="Q4_SEARCH",
                sql_name="search_fuzzy",
                params={"query": "테헤란로임의불일치", "limit": 10},
                label="테헤란로",
                source="synthetic",
            ),
        )
    )

    assert cases[0].path == "/v1/address/geocode"
    assert cases[0].params["address"] == "서울특별시 강남구 테헤란로 152-3"
    assert cases[0].params["type"] == "road"
    assert cases[1].params["address"] == "강원특별자치도 춘천시 신북읍 산 12-3"
    assert cases[1].params["type"] == "parcel"
    assert cases[2].params["address"] == "테헤란길 152"
    assert cases[2].params["sig_cd"] == "11680"
    assert cases[3].path == "/v1/address/search"
    assert cases[3].sql_name == "search_fuzzy"
    assert cases[3].params["query"] == "테헤란로임의불일치"


def test_address_helpers_preserve_parseable_road_suffixes() -> None:
    params: Params = {
        "si": "서울특별시",
        "sgg": "중구",
        "road_nrm": "퇴계로",
        "mnnm": 88,
        "slno": 0,
        "buld_se_cd": "1",
        "emd": "필동",
        "mntn_yn": "0",
    }

    assert _road_address(params) == "서울특별시 중구 지하 퇴계로 88"
    assert _parcel_address({**params, "mnnm": 10, "slno": 2}) == "서울특별시 중구 필동 10-2"
    assert _fuzzy_address(params) == "서울특별시 중구 퇴계길 88"


def test_summarize_api_measurements_ignores_warmup() -> None:
    measurements = (
        ApiMeasurement(
            case_id="warm",
            group="Q1",
            sql_name="geocode_road",
            concurrency=1,
            iteration=1,
            warmup=True,
            ok=True,
            elapsed_ms=1000.0,
            http_status=200,
            app_status="OK",
            response_bytes=100,
        ),
        ApiMeasurement(
            case_id="a",
            group="Q1",
            sql_name="geocode_road",
            concurrency=1,
            iteration=2,
            warmup=False,
            ok=True,
            elapsed_ms=10.0,
            http_status=200,
            app_status="OK",
            response_bytes=100,
        ),
        ApiMeasurement(
            case_id="b",
            group="Q1",
            sql_name="geocode_road",
            concurrency=1,
            iteration=2,
            warmup=False,
            ok=True,
            elapsed_ms=20.0,
            http_status=200,
            app_status="OK",
            response_bytes=200,
        ),
    )

    (summary,) = summarize(measurements)
    assert summary.samples == 2
    assert summary.errors == 0
    assert summary.p50_ms == 15.0
    assert summary.avg_response_bytes == 150.0


def test_parse_server_profile_records_key_value_pairs() -> None:
    assert parse_server_profile(("workers=4", "pool=20/64", "query_metrics=false")) == {
        "pool": "20/64",
        "query_metrics": "false",
        "workers": "4",
    }
