"""Python client and data loader for Korean Juso address information."""

from __future__ import annotations

from .client import KrAddrClient
from .data import (
    ROAD_NAME_KOREAN_DETAIL_SN,
    RoadNameAddressDataClient,
    archive_standard_date,
    iter_related_jibun_records,
    iter_road_name_address_records,
    load_related_jibun_records,
    load_road_name_address_records,
)
from .exceptions import (
    KrAddrAuthError,
    KrAddrError,
    KrAddrNoDataError,
    KrAddrParseError,
    KrAddrRateLimitError,
    KrAddrRequestError,
    KrAddrServerError,
)
from .legal_dong import (
    DATA_GO_KR_LEGAL_DONG_PAGE_URL,
    DataGoKrLegalDongClient,
    iter_legal_dong_records,
    load_legal_dong_records,
    records_from_openapi_rows,
)
from .models import (
    AddressCoordinate,
    AddressSearchResult,
    DatasetFile,
    DetailAddress,
    EnglishAddressSearchResult,
    JusoPage,
    LegalDongRecord,
    RelatedJibunRecord,
    RoadNameAddressKoreanRecord,
)
from .postgis import BoundaryLoadResult, PostGISLegalDongStore, make_postgis_metadata
from .store import RoadNameAddressStore

JusoClient = KrAddrClient

__all__ = [
    "AddressCoordinate",
    "AddressSearchResult",
    "BoundaryLoadResult",
    "DATA_GO_KR_LEGAL_DONG_PAGE_URL",
    "DataGoKrLegalDongClient",
    "DatasetFile",
    "DetailAddress",
    "EnglishAddressSearchResult",
    "JusoClient",
    "JusoPage",
    "KrAddrAuthError",
    "KrAddrClient",
    "KrAddrError",
    "KrAddrNoDataError",
    "KrAddrParseError",
    "KrAddrRateLimitError",
    "KrAddrRequestError",
    "KrAddrServerError",
    "LegalDongRecord",
    "ROAD_NAME_KOREAN_DETAIL_SN",
    "RelatedJibunRecord",
    "RoadNameAddressDataClient",
    "RoadNameAddressKoreanRecord",
    "RoadNameAddressStore",
    "PostGISLegalDongStore",
    "archive_standard_date",
    "iter_related_jibun_records",
    "iter_legal_dong_records",
    "iter_road_name_address_records",
    "load_legal_dong_records",
    "load_related_jibun_records",
    "load_road_name_address_records",
    "make_postgis_metadata",
    "records_from_openapi_rows",
]
