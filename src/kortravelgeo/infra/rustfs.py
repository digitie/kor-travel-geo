"""RustFS/S3-compatible object storage helpers for admin uploads."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

import anyio
import httpx

from kortravelgeo.dto.admin import (
    RustfsConnectionCheck,
    RustfsSecretStatus,
    RustfsStorageConfig,
    RustfsStorageConfigPatch,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError
from kortravelgeo.settings import Settings

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_SERVICE = "s3"
_AWS4_REQUEST = "aws4_request"
_UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"

#: Async transport hook. Given a fully signed request it returns an
#: :class:`httpx.Response`. The default (:func:`_httpx_send`) issues a real
#: HTTP call; tests inject a fake to exercise the multipart logic without a
#: live RustFS bucket (ADR-044/045: this project connects to an existing
#: bucket, it does not run RustFS, so live calls cannot be unit-tested).
RustfsSender = Callable[
    [str, str, dict[str, str], "bytes | AsyncIterator[bytes] | None"],
    Awaitable[httpx.Response],
]


@dataclass(frozen=True)
class EffectiveRustfsConfig:
    enabled: bool
    endpoint_url: str
    bucket: str
    prefix: str
    region: str
    force_path_style: bool
    retention_days: int
    access_key: str | None
    secret_key: str | None

    @property
    def credentials_configured(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def object_key(self, *parts: str | Path) -> str:
        return join_object_key(self.prefix, *parts)

    def upload_set_prefix(self, upload_set_id: str) -> str:
        return self.object_key("uploads", upload_set_id)

    def upload_set_uri(self, upload_set_id: str) -> str:
        return rustfs_uri(self.bucket, self.upload_set_prefix(upload_set_id))


@dataclass(frozen=True)
class RustfsObject:
    key: str
    size: int
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class RustfsObjectHead:
    """``head_object`` result: size/etag/version + ``x-amz-meta-*`` metadata."""

    key: str
    size: int
    etag: str | None = None
    version_id: str | None = None
    last_modified: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RustfsUploadedPart:
    """One ``upload_part`` result, recorded on the upload session for resume."""

    part_number: int
    etag: str


@dataclass(frozen=True)
class RustfsListedPart:
    """One entry from ``ListParts`` on an in-progress multipart upload."""

    part_number: int
    etag: str | None = None
    size: int | None = None


class RustfsClient:
    """Small SigV4 S3 client for RustFS basic object operations."""

    def __init__(
        self,
        config: EffectiveRustfsConfig,
        *,
        sender: RustfsSender | None = None,
    ) -> None:
        if not config.force_path_style:
            msg = "RustFS path-style endpoint만 지원합니다"
            raise InvalidInputError(msg)
        if not config.credentials_configured:
            msg = "RustFS access key와 secret key가 설정되어 있지 않습니다"
            raise InvalidInputError(msg)
        self._config = config
        self._endpoint = config.endpoint_url.rstrip("/")
        self._parsed_endpoint = urlsplit(self._endpoint)
        if (
            self._parsed_endpoint.scheme not in {"http", "https"}
            or not self._parsed_endpoint.netloc
        ):
            msg = f"invalid RustFS endpoint_url: {config.endpoint_url}"
            raise InvalidInputError(msg)
        self._sender: RustfsSender = sender or _httpx_send

    async def ensure_bucket(self) -> None:
        head = await self._request(
            "HEAD",
            bucket=self._config.bucket,
            expected_status=(200, 404),
        )
        if head.status_code == 200:
            return
        put = await self._request(
            "PUT",
            bucket=self._config.bucket,
            expected_status=(200, 201, 204, 409),
        )
        if put.status_code == 409 and "BucketAlready" not in put.text:
            raise InvalidInputError(_rustfs_error_message(put))

    async def check(self) -> RustfsConnectionCheck:
        try:
            await self.ensure_bucket()
        except Exception as exc:
            return RustfsConnectionCheck(
                ok=False,
                endpoint_url=self._config.endpoint_url,
                bucket=self._config.bucket,
                prefix=self._config.prefix,
                message=str(exc),
            )
        return RustfsConnectionCheck(
            ok=True,
            endpoint_url=self._config.endpoint_url,
            bucket=self._config.bucket,
            prefix=self._config.prefix,
            message="bucket 접근이 가능합니다.",
        )

    async def put_file(
        self,
        key: str,
        path: Path,
        *,
        sha256: str | None = None,
    ) -> str | None:
        digest = sha256 or await sha256_file(path)
        stat = await anyio.Path(path).stat()
        headers = {
            "content-length": str(stat.st_size),
            "content-type": "application/octet-stream",
            "x-amz-content-sha256": digest,
        }
        response = await self._request(
            "PUT",
            bucket=self._config.bucket,
            key=key,
            headers=headers,
            content=_read_file_chunks(path),
            payload_hash=digest,
            expected_status=(200, 201, 204),
        )
        return _strip_etag(response.headers.get("etag"))

    async def download_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + ".part")
        url, headers = self._signed_request(
            "GET",
            bucket=self._config.bucket,
            key=key,
            payload_hash=_EMPTY_SHA256,
        )
        timeout = httpx.Timeout(60.0, connect=10.0, read=None, write=None, pool=10.0)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            if response.status_code != 200:
                text = await response.aread()
                decoded = text.decode("utf-8", "replace")
                raise InvalidInputError(
                    _rustfs_error_message_from_text(response.status_code, decoded)
                )
            async with await anyio.open_file(part, "wb") as fh:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        await fh.write(chunk)
        part.replace(destination)

    async def list_objects(
        self, prefix: str, *, limit: int | None = None
    ) -> tuple[RustfsObject, ...]:
        normalized_prefix = normalize_object_prefix(prefix)
        objects: list[RustfsObject] = []
        continuation: str | None = None
        while True:
            query = {
                "list-type": "2",
                "prefix": normalized_prefix,
            }
            if continuation:
                query["continuation-token"] = continuation
            response = await self._request(
                "GET",
                bucket=self._config.bucket,
                query=query,
                expected_status=(200,),
            )
            batch, continuation = _parse_list_objects_response(response.text)
            objects.extend(batch)
            if limit is not None and len(objects) > limit:
                msg = f"RustFS object scan limit exceeded: {len(objects)} > {limit}"
                raise InvalidInputError(msg)
            if continuation is None:
                return tuple(objects)

    async def head_object(self, key: str) -> RustfsObjectHead:
        """HEAD an object: size/etag/version + ``x-amz-meta-*`` metadata.

        Per the t109 doc, SHA-256 is never assumed equal to the ETag; callers
        compare ``head`` values to the upload-session record and only re-read the
        body (:meth:`rehash`) when they differ.
        """
        response = await self._request(
            "HEAD",
            bucket=self._config.bucket,
            key=key,
            expected_status=(200, 404),
        )
        if response.status_code == 404:
            raise NotFoundError(f"RustFS object not found: {key}")
        metadata = {
            name[len("x-amz-meta-") :]: value
            for name, value in response.headers.items()
            if name.lower().startswith("x-amz-meta-")
        }
        return RustfsObjectHead(
            key=key,
            size=_required_non_negative_int(
                response.headers.get("content-length"),
                "content-length",
                "RustFS HEAD",
            ),
            etag=_strip_etag(response.headers.get("etag")),
            version_id=response.headers.get("x-amz-version-id"),
            last_modified=response.headers.get("last-modified"),
            metadata=metadata,
        )

    async def delete_object(self, key: str) -> None:
        """Hard-delete an object (reconciliation / abort cleanup)."""
        await self._request(
            "DELETE",
            bucket=self._config.bucket,
            key=key,
            expected_status=(200, 202, 204, 404),
        )

    async def create_multipart_upload(
        self,
        key: str,
        *,
        metadata: dict[str, str] | None = None,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Initiate a multipart upload and return its ``UploadId``."""
        headers = {"content-type": content_type}
        for name, value in (metadata or {}).items():
            headers[f"x-amz-meta-{name}"] = value
        response = await self._request(
            "POST",
            bucket=self._config.bucket,
            key=key,
            query={"uploads": ""},
            headers=headers,
            expected_status=(200,),
        )
        upload_id = _xml_text(ElementTree.fromstring(response.text), "UploadId")
        if not upload_id:
            msg = "RustFS create_multipart_upload returned no UploadId"
            raise InvalidInputError(msg)
        return upload_id

    async def upload_part(
        self,
        key: str,
        *,
        upload_id: str,
        part_number: int,
        body: bytes,
    ) -> RustfsUploadedPart:
        """Upload one part; return its part number and ETag for completion."""
        if part_number < 1:
            msg = "part_number must be >= 1"
            raise InvalidInputError(msg)
        payload_hash = hashlib.sha256(body).hexdigest()
        response = await self._request(
            "PUT",
            bucket=self._config.bucket,
            key=key,
            query={"partNumber": str(part_number), "uploadId": upload_id},
            headers={
                "content-length": str(len(body)),
                "x-amz-content-sha256": payload_hash,
            },
            content=body,
            payload_hash=payload_hash,
            expected_status=(200,),
        )
        etag = _strip_etag(response.headers.get("etag"))
        if not etag:
            msg = "RustFS upload_part returned no ETag"
            raise InvalidInputError(msg)
        return RustfsUploadedPart(part_number=part_number, etag=etag)

    async def complete_multipart_upload(
        self,
        key: str,
        *,
        upload_id: str,
        parts: tuple[RustfsUploadedPart, ...],
    ) -> str | None:
        """Complete the upload; return the final object ETag if reported."""
        if not parts:
            msg = "complete_multipart_upload requires at least one part"
            raise InvalidInputError(msg)
        body = _complete_multipart_body(parts)
        payload_hash = hashlib.sha256(body).hexdigest()
        response = await self._request(
            "POST",
            bucket=self._config.bucket,
            key=key,
            query={"uploadId": upload_id},
            headers={
                "content-length": str(len(body)),
                "content-type": "application/xml",
                "x-amz-content-sha256": payload_hash,
            },
            content=body,
            payload_hash=payload_hash,
            expected_status=(200,),
        )
        # S3 may return a 200 wrapping an <Error>; surface it instead of success.
        code = _extract_s3_error_code(response.text)
        if code:
            raise InvalidInputError(f"RustFS complete_multipart_upload failed: {code}")
        return _strip_etag(_xml_text(ElementTree.fromstring(response.text), "ETag"))

    async def abort_multipart_upload(self, key: str, *, upload_id: str) -> None:
        """Abort an in-progress multipart upload, discarding uploaded parts."""
        await self._request(
            "DELETE",
            bucket=self._config.bucket,
            key=key,
            query={"uploadId": upload_id},
            expected_status=(200, 204, 404),
        )

    async def list_parts(
        self,
        key: str,
        *,
        upload_id: str,
    ) -> tuple[RustfsListedPart, ...]:
        """ListParts for a multipart upload.

        Raises :class:`NotFoundError` (HTTP 404 ``NoSuchUpload``) when the
        upload id no longer exists, which the session resume path translates to
        the ``failed_storage_state`` transition.
        """
        parts: list[RustfsListedPart] = []
        marker: str | None = None
        while True:
            query = {"uploadId": upload_id}
            if marker:
                query["part-number-marker"] = marker
            response = await self._request(
                "GET",
                bucket=self._config.bucket,
                key=key,
                query=query,
                expected_status=(200, 404),
            )
            if response.status_code == 404:
                raise NotFoundError(f"multipart upload not found: {upload_id}")
            batch, marker = _parse_list_parts_response(response.text)
            parts.extend(batch)
            if marker is None:
                return tuple(parts)

    async def rehash(self, key: str) -> str:
        """Stream the object body and return its SHA-256 (no ETag shortcut)."""
        url, headers = self._signed_request(
            "GET",
            bucket=self._config.bucket,
            key=key,
            payload_hash=_EMPTY_SHA256,
        )
        digest = hashlib.sha256()
        timeout = httpx.Timeout(60.0, connect=10.0, read=None, write=None, pool=10.0)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            if response.status_code != 200:
                text = await response.aread()
                raise InvalidInputError(
                    _rustfs_error_message_from_text(
                        response.status_code, text.decode("utf-8", "replace")
                    )
                )
            async for chunk in response.aiter_bytes():
                if chunk:
                    digest.update(chunk)
        return digest.hexdigest()

    async def compute_sha256(self, key: str) -> str:
        """Alias for :meth:`rehash` (t109 doc name ``rehash_object``)."""
        return await self.rehash(key)

    async def _request(
        self,
        method: str,
        *,
        bucket: str | None = None,
        key: str | None = None,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | AsyncIterator[bytes] | None = None,
        payload_hash: str = _EMPTY_SHA256,
        expected_status: tuple[int, ...],
    ) -> httpx.Response:
        url, signed_headers = self._signed_request(
            method,
            bucket=bucket,
            key=key,
            query=query,
            headers=headers,
            payload_hash=payload_hash,
        )
        response = await self._sender(method, url, signed_headers, content)
        if response.status_code not in expected_status:
            raise InvalidInputError(_rustfs_error_message(response))
        return response

    def _signed_request(
        self,
        method: str,
        *,
        bucket: str | None = None,
        key: str | None = None,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        payload_hash: str = _EMPTY_SHA256,
    ) -> tuple[str, dict[str, str]]:
        method = method.upper()
        request_time = datetime.now(UTC)
        amz_date = request_time.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = request_time.strftime("%Y%m%d")
        canonical_uri = self._canonical_uri(bucket=bucket, key=key)
        canonical_query = canonical_query_string(query or {})
        url = f"{self._endpoint}{canonical_uri}"
        if canonical_query:
            url = f"{url}?{canonical_query}"

        request_headers: dict[str, str] = {
            "host": self._parsed_endpoint.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        for name, value in (headers or {}).items():
            request_headers[name.lower()] = value.strip()

        canonical_headers = "".join(
            f"{name}:{_canonical_header_value(value)}\n"
            for name, value in sorted(request_headers.items())
        )
        signed_headers = ";".join(sorted(request_headers))
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self._config.region}/{_SERVICE}/{_AWS4_REQUEST}"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _signing_key(self._config.secret_key or "", date_stamp, self._config.region)
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request_headers["authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self._config.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        return url, request_headers

    @staticmethod
    def _canonical_uri(*, bucket: str | None, key: str | None) -> str:
        parts: list[str] = []
        if bucket:
            parts.append(quote(bucket, safe="-_.~"))
        if key:
            parts.extend(quote(part, safe="-_.~") for part in key.split("/"))
        return "/" + "/".join(parts)


def load_rustfs_config(settings: Settings) -> EffectiveRustfsConfig:
    file_config = _read_config_file(settings.rustfs_config_path)
    return EffectiveRustfsConfig(
        enabled=bool(file_config.get("enabled", settings.rustfs_enabled)),
        endpoint_url=str(file_config.get("endpoint_url", settings.rustfs_endpoint_url)).rstrip("/"),
        bucket=str(file_config.get("bucket", settings.rustfs_bucket)),
        prefix=normalize_object_prefix(str(file_config.get("prefix", settings.rustfs_prefix))),
        region=str(file_config.get("region", settings.rustfs_region)),
        force_path_style=bool(
            file_config.get("force_path_style", settings.rustfs_force_path_style)
        ),
        retention_days=_config_int(
            file_config.get("retention_days"),
            settings.rustfs_retention_days,
        ),
        access_key=_secret_value(file_config.get("access_key"))
        or _settings_secret(settings.rustfs_access_key),
        secret_key=_secret_value(file_config.get("secret_key"))
        or _settings_secret(settings.rustfs_secret_key),
    )


def describe_rustfs_config(config: EffectiveRustfsConfig) -> RustfsStorageConfig:
    return RustfsStorageConfig(
        enabled=config.enabled,
        endpoint_url=config.endpoint_url,
        bucket=config.bucket,
        prefix=config.prefix,
        region=config.region,
        force_path_style=config.force_path_style,
        retention_days=config.retention_days,
        access_key=_secret_status(config.access_key),
        secret_key=_secret_status(config.secret_key),
    )


def save_rustfs_config(settings: Settings, patch: RustfsStorageConfigPatch) -> RustfsStorageConfig:
    current = _read_config_file(settings.rustfs_config_path)
    payload = dict(current)
    updates = patch.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key in {"endpoint_url", "prefix"} and isinstance(value, str):
            value = value.rstrip("/") if key == "endpoint_url" else normalize_object_prefix(value)
        payload[key] = value
    _write_config_file(settings.rustfs_config_path, payload)
    return describe_rustfs_config(load_rustfs_config(settings))


def require_enabled_rustfs(settings: Settings) -> EffectiveRustfsConfig:
    config = load_rustfs_config(settings)
    if not config.enabled:
        msg = "RustFS 저장소가 비활성화되어 있습니다"
        raise InvalidInputError(msg)
    if not config.credentials_configured:
        msg = "RustFS access key와 secret key가 설정되어 있지 않습니다"
        raise InvalidInputError(msg)
    return config


def rustfs_uri(bucket: str, key: str) -> str:
    return f"rustfs://{bucket}/{normalize_object_prefix(key)}"


def normalize_object_prefix(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    parts = [
        part
        for part in PurePosixPath(normalized).parts
        if part not in {"", ".", "..", "/"} and ":" not in part
    ]
    return str(PurePosixPath(*parts)) if parts else "kor-travel-geo"


def join_object_key(*parts: str | Path) -> str:
    joined: list[str] = []
    for part in parts:
        text = str(part).replace("\\", "/").strip("/")
        if not text:
            continue
        joined.append(normalize_object_prefix(text))
    return str(PurePosixPath(*joined)) if joined else "kor-travel-geo"


async def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    async with await anyio.open_file(path, "rb") as fh:
        while True:
            chunk = await fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


async def _read_file_chunks(path: Path) -> AsyncIterator[bytes]:
    async with await anyio.open_file(path, "rb") as fh:
        while True:
            chunk = await fh.read(1024 * 1024)
            if not chunk:
                break
            yield chunk


async def _httpx_send(
    method: str,
    url: str,
    headers: dict[str, str],
    content: bytes | AsyncIterator[bytes] | None,
) -> httpx.Response:
    """Default :data:`RustfsSender`: issue a real signed HTTP request."""
    timeout = httpx.Timeout(60.0, connect=10.0, read=None, write=None, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.request(method, url, headers=headers, content=content)


def _complete_multipart_body(parts: tuple[RustfsUploadedPart, ...]) -> bytes:
    ordered = sorted(parts, key=lambda part: part.part_number)
    rows = "".join(
        f"<Part><PartNumber>{part.part_number}</PartNumber>"
        f"<ETag>{_quote_etag(part.etag)}</ETag></Part>"
        for part in ordered
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<CompleteMultipartUpload xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"{rows}</CompleteMultipartUpload>"
    ).encode()


def _quote_etag(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped
    return f'"{stripped}"'


def _parse_list_parts_response(payload: str) -> tuple[tuple[RustfsListedPart, ...], str | None]:
    root = ElementTree.fromstring(payload)
    parts: list[RustfsListedPart] = []
    for item in root.findall(".//{*}Part"):
        number_text = _xml_text(item, "PartNumber")
        if number_text is None:
            continue
        size_text = _xml_text(item, "Size")
        parts.append(
            RustfsListedPart(
                part_number=int(number_text),
                etag=_strip_etag(_xml_text(item, "ETag")),
                size=int(size_text) if size_text is not None else None,
            )
        )
    truncated = (_xml_text(root, "IsTruncated") or "").lower() == "true"
    marker = _xml_text(root, "NextPartNumberMarker") if truncated else None
    return tuple(parts), marker


def canonical_query_string(query: dict[str, str]) -> str:
    pairs = []
    for key, value in sorted(query.items()):
        pairs.append(f"{quote(key, safe='-_.~')}={quote(value, safe='-_.~')}")
    return "&".join(pairs)


def _canonical_header_value(value: str) -> str:
    return " ".join(value.split())


def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    date_key = hmac.new(
        f"AWS4{secret_key}".encode(),
        date_stamp.encode(),
        hashlib.sha256,
    ).digest()
    region_key = hmac.new(date_key, region.encode(), hashlib.sha256).digest()
    service_key = hmac.new(region_key, _SERVICE.encode(), hashlib.sha256).digest()
    return hmac.new(service_key, _AWS4_REQUEST.encode(), hashlib.sha256).digest()


def _parse_list_objects_response(payload: str) -> tuple[tuple[RustfsObject, ...], str | None]:
    root = ElementTree.fromstring(payload)
    objects: list[RustfsObject] = []
    for item in root.findall(".//{*}Contents"):
        key = _xml_text(item, "Key")
        if not key or key.endswith("/"):
            continue
        size_text = _xml_text(item, "Size")
        objects.append(
            RustfsObject(
                key=key,
                size=_required_non_negative_int(
                    size_text,
                    "Size",
                    "RustFS ListObjectsV2",
                ),
                etag=_strip_etag(_xml_text(item, "ETag")),
                last_modified=_xml_text(item, "LastModified"),
            )
        )
    truncated = (_xml_text(root, "IsTruncated") or "").lower() == "true"
    continuation = _xml_text(root, "NextContinuationToken") if truncated else None
    return tuple(objects), continuation


def _xml_text(element: ElementTree.Element, name: str) -> str | None:
    child = element.find(f"{{*}}{name}")
    if child is None or child.text is None:
        return None
    return child.text


def _strip_etag(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    return stripped or None


def _secret_status(value: str | None) -> RustfsSecretStatus:
    if not value:
        return RustfsSecretStatus(configured=False)
    hint = value[-4:] if len(value) >= 4 else None
    return RustfsSecretStatus(configured=True, hint=hint)


def _settings_secret(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        secret = value.get_secret_value()
        return str(secret) if secret else None
    text = str(value)
    return text or None


def _secret_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _config_int(value: object, default: int) -> int:
    if value is None:
        return default
    return int(str(value))


def _read_config_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"invalid RustFS config file: {path}"
        raise InvalidInputError(msg)
    return data


def _write_config_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with suppress(PermissionError):
        path.chmod(0o600)


def _rustfs_error_message(response: httpx.Response) -> str:
    return _rustfs_error_message_from_text(response.status_code, response.text)


def _rustfs_error_message_from_text(status_code: int, text: str) -> str:
    code = _extract_s3_error_code(text)
    if code:
        return f"RustFS request failed: HTTP {status_code} {code}"
    return f"RustFS request failed: HTTP {status_code}"


def _extract_s3_error_code(payload: str) -> str | None:
    if not payload.strip():
        return None
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return None
    return _xml_text(root, "Code")


def _required_non_negative_int(
    value: str | None,
    name: str,
    context: str,
) -> int:
    if value is None or value == "":
        raise InvalidInputError(f"{context} response missing {name}")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise InvalidInputError(f"{context} response has invalid {name}: {value!r}") from exc
    if parsed < 0:
        raise InvalidInputError(f"{context} response has negative {name}: {value!r}")
    return parsed
