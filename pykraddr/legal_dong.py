"""data.go.kr legal-dong code download and CSV parsing helpers."""

from __future__ import annotations

import codecs
import csv
import io
import os
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from itertools import chain
from pathlib import Path
from typing import Any

from ._http import SessionLike, build_session, raise_for_http_error, response_json, without_none
from .exceptions import KrAddrParseError
from .models import LegalDongRecord

DATA_GO_KR_LEGAL_DONG_PAGE_URL = (
    "https://www.data.go.kr/tcs/dss/selectFileDataDetailView.do?publicDataPk=15063424"
)

LEGAL_DONG_FIELD_ALIASES = {
    "legal_dong_code": ("법정동코드", "법정동 코드", "bjd_cd", "bjcd", "code"),
    "legal_dong_name": ("법정동명", "법정동 명", "법정동", "bjd_nm", "name"),
    "status_name": ("폐지여부", "존재여부", "상태", "status", "use_yn"),
    "previous_legal_dong_code": ("과거법정동코드", "이전법정동코드", "old_code"),
    "sido_name": ("시도명", "시도", "sido_nm"),
    "sigungu_name": ("시군구명", "시군구", "sigungu_nm"),
    "eup_myeon_dong_name": ("읍면동명", "읍면동", "emd_nm"),
    "ri_name": ("리명", "리", "ri_nm"),
}


class DataGoKrLegalDongClient:
    """Small helper for data.go.kr legal-dong file/API retrieval.

    The file page can be downloaded manually without login, while the
    auto-converted OpenAPI requires a data.go.kr service key. This client keeps
    both paths explicit: use ``download_file`` for a known CSV URL, or
    ``iter_openapi_rows`` with the OpenAPI URL issued by data.go.kr.
    """

    def __init__(
        self,
        *,
        service_key: str | None = None,
        timeout: float = 60.0,
        retries: int = 3,
        session: SessionLike | None = None,
    ) -> None:
        self.service_key = service_key
        self.timeout = timeout
        self.session = session or build_session(retries)

    @classmethod
    def from_env(cls, env_var: str = "DATA_GO_KR_SERVICE_KEY") -> DataGoKrLegalDongClient:
        return cls(service_key=os.getenv(env_var))

    def download_file(
        self,
        url: str,
        output_path: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download a known data.go.kr CSV/ZIP file URL."""

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return path
        response = self.session.get(url, timeout=self.timeout, stream=True)
        raise_for_http_error(response, "download legal dong file")
        path.write_bytes(bytes(response.content))
        return path

    def iter_openapi_rows(
        self,
        api_url: str,
        *,
        service_key: str | None = None,
        per_page: int = 1000,
        extra_params: Mapping[str, Any] | None = None,
    ) -> Iterator[Mapping[str, Any]]:
        """Yield rows from a data.go.kr auto-converted OpenAPI endpoint.

        data.go.kr exposes file datasets as JSON APIs after 활용신청. The exact
        endpoint contains an API-specific path, so callers pass the issued
        ``api_url`` instead of relying on a hard-coded URL.
        """

        key = service_key or self.service_key
        if not key:
            raise ValueError("data.go.kr service key is required for OpenAPI retrieval")
        page = 1
        while True:
            params = {
                "serviceKey": key,
                "page": page,
                "perPage": per_page,
                "returnType": "JSON",
            }
            params.update(extra_params or {})
            response = self.session.get(
                api_url,
                params=without_none(params),
                timeout=self.timeout,
            )
            raise_for_http_error(response, "fetch legal dong OpenAPI rows")
            payload = response_json(response, "fetch legal dong OpenAPI rows")
            rows = _extract_rows(payload)
            if not rows:
                return
            yield from rows
            total_count = _int_or_none(payload.get("totalCount") or payload.get("total_count"))
            if total_count is not None and page * per_page >= total_count:
                return
            if len(rows) < per_page:
                return
            page += 1


def load_legal_dong_records(
    path: str | os.PathLike[str] | bytes,
    *,
    encoding: str | None = None,
) -> list[LegalDongRecord]:
    return list(iter_legal_dong_records(path, encoding=encoding))


def iter_legal_dong_records(
    path: str | os.PathLike[str] | bytes,
    *,
    encoding: str | None = None,
) -> Iterator[LegalDongRecord]:
    """Stream legal-dong code rows from a CSV file or ZIP containing CSV files."""

    for member in _iter_csv_members(_content_bytes(path)):
        selected = _choose_encoding(member.content, encoding)
        text = io.TextIOWrapper(io.BytesIO(member.content), encoding=selected, newline="")
        reader = csv.DictReader(text)
        if not reader.fieldnames:
            continue
        header_map = _header_map(reader.fieldnames)
        if "legal_dong_code" not in header_map:
            raise KrAddrParseError(f"{member.name}: legal dong code column was not found")
        for raw_row in reader:
            normalized = _normalize_row(raw_row, header_map)
            code = normalized.get("legal_dong_code", "")
            if not code:
                continue
            yield LegalDongRecord(
                legal_dong_code=code,
                legal_dong_name=_legal_name(normalized),
                status_name=normalized.get("status_name", ""),
                previous_legal_dong_code=normalized.get("previous_legal_dong_code") or None,
                sido_name=normalized.get("sido_name") or None,
                sigungu_name=normalized.get("sigungu_name") or None,
                eup_myeon_dong_name=normalized.get("eup_myeon_dong_name") or None,
                ri_name=normalized.get("ri_name") or None,
                raw=raw_row,
            )


def records_from_openapi_rows(rows: Iterable[Mapping[str, Any]]) -> Iterator[LegalDongRecord]:
    """Normalize rows already fetched from data.go.kr JSON/XML converted APIs."""

    rows = iter(rows)
    try:
        first = next(rows)
    except StopIteration:
        return
    header_map = _header_map([str(key) for key in first.keys()])
    for raw_row in chain((first,), rows):
        normalized = _normalize_row(raw_row, header_map)
        code = normalized.get("legal_dong_code", "")
        if not code:
            continue
        yield LegalDongRecord(
            legal_dong_code=code,
            legal_dong_name=_legal_name(normalized),
            status_name=normalized.get("status_name", ""),
            previous_legal_dong_code=normalized.get("previous_legal_dong_code") or None,
            sido_name=normalized.get("sido_name") or None,
            sigungu_name=normalized.get("sigungu_name") or None,
            eup_myeon_dong_name=normalized.get("eup_myeon_dong_name") or None,
            ri_name=normalized.get("ri_name") or None,
            raw=raw_row,
        )


class _CsvMember:
    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self.content = content


def _content_bytes(path: str | os.PathLike[str] | bytes) -> bytes:
    if isinstance(path, bytes):
        return path
    return Path(path).read_bytes()


def _iter_csv_members(content: bytes) -> Iterator[_CsvMember]:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        yield _CsvMember("data.csv", content)
        return
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".csv"):
                yield _CsvMember(name, archive.read(name))


def _choose_encoding(content: bytes, encoding: str | None) -> str:
    candidates: Iterable[str] = (encoding,) if encoding else ("utf-8-sig", "cp949", "euc-kr")
    last_error: UnicodeDecodeError | None = None
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            decoder = codecs.getincrementaldecoder(candidate)()
            decoder.decode(content, final=True)
            return candidate
        except UnicodeDecodeError as exc:
            last_error = exc
    raise KrAddrParseError("legal dong CSV encoding could not be decoded") from last_error


def _header_map(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {_normalize_header(name): name for name in fieldnames}
    mapped: dict[str, str] = {}
    for target, aliases in LEGAL_DONG_FIELD_ALIASES.items():
        for alias in aliases:
            source = normalized.get(_normalize_header(alias))
            if source is not None:
                mapped[target] = source
                break
    return mapped


def _normalize_row(row: Mapping[str, Any], header_map: Mapping[str, str]) -> dict[str, str]:
    return {
        target: _clean(row.get(source))
        for target, source in header_map.items()
        if source in row and _clean(row.get(source))
    }


def _legal_name(row: Mapping[str, str]) -> str:
    explicit = row.get("legal_dong_name", "")
    if explicit:
        return explicit
    parts = [
        row.get("sido_name", ""),
        row.get("sigungu_name", ""),
        row.get("eup_myeon_dong_name", ""),
        row.get("ri_name", ""),
    ]
    return " ".join(part for part in parts if part)


def _normalize_header(value: str) -> str:
    return _clean(value).replace(" ", "").replace("_", "").lower().lstrip("\ufeff")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list) and all(isinstance(row, Mapping) for row in data):
        return data
    response = payload.get("response")
    if isinstance(response, Mapping):
        body = response.get("body")
        if isinstance(body, Mapping):
            items = body.get("items")
            if isinstance(items, Mapping):
                item = items.get("item")
                if isinstance(item, list) and all(isinstance(row, Mapping) for row in item):
                    return item
                if isinstance(item, Mapping):
                    return [item]
    raise KrAddrParseError("legal dong OpenAPI response did not contain rows")


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
