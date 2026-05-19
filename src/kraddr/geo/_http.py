"""HTTP helpers for Juso and data.go.kr calls."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any, Protocol

import httpx

from .exceptions import (
    KrAddrAuthError,
    KrAddrParseError,
    KrAddrRateLimitError,
    KrAddrRequestError,
    KrAddrServerError,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; python-kraddr-geo/0.1; +https://business.juso.go.kr)"
)
TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


class ResponseLike(Protocol):
    status_code: int
    headers: Any
    encoding: Any

    @property
    def text(self) -> str: ...

    @property
    def content(self) -> bytes: ...

    def json(self) -> Any: ...


class SessionLike(Protocol):
    headers: Any

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ResponseLike: ...

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> ResponseLike: ...


class AsyncSessionLike(Protocol):
    headers: Any

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ResponseLike: ...

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> ResponseLike: ...


class SyncHttpxSession:
    """Small requests-compatible facade backed by httpx.Client."""

    def __init__(
        self,
        *,
        retries: int = 3,
        timeout: float | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.retries = retries
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self.headers = self._client.headers

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ResponseLike:
        return self._request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            stream=stream,
        )

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> ResponseLike:
        return self._request("POST", url, json=json, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ResponseLike:
        attempts = max(1, self.retries + 1)
        last_error: httpx.HTTPError | None = None
        for attempt in range(attempts):
            try:
                if stream:
                    request = self._client.build_request(
                        method,
                        url,
                        params=params,
                        json=json,
                        headers=headers,
                        timeout=timeout,
                    )
                    response = self._client.send(request, stream=True)
                else:
                    response = self._client.request(
                        method,
                        url,
                        params=params,
                        json=json,
                        headers=headers,
                        timeout=timeout,
                    )
                if response.status_code in TRANSIENT_STATUSES and attempt < attempts - 1:
                    response.close()
                    time.sleep(_backoff_seconds(attempt))
                    continue
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                time.sleep(_backoff_seconds(attempt))
        raise KrAddrRequestError(f"HTTP request failed: {last_error}") from last_error


class AsyncHttpxSession:
    """Async requests-compatible facade backed by httpx.AsyncClient."""

    def __init__(
        self,
        *,
        retries: int = 3,
        timeout: float | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.retries = retries
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self.headers = self._client.headers

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ResponseLike:
        return await self._request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            stream=stream,
        )

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> ResponseLike:
        return await self._request("POST", url, json=json, headers=headers, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ResponseLike:
        attempts = max(1, self.retries + 1)
        last_error: httpx.HTTPError | None = None
        for attempt in range(attempts):
            try:
                if stream:
                    request = self._client.build_request(
                        method,
                        url,
                        params=params,
                        json=json,
                        headers=headers,
                        timeout=timeout,
                    )
                    response = await self._client.send(request, stream=True)
                else:
                    response = await self._client.request(
                        method,
                        url,
                        params=params,
                        json=json,
                        headers=headers,
                        timeout=timeout,
                    )
                if response.status_code in TRANSIENT_STATUSES and attempt < attempts - 1:
                    await response.aclose()
                    await asyncio.sleep(_backoff_seconds(attempt))
                    continue
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(_backoff_seconds(attempt))
        raise KrAddrRequestError(f"HTTP request failed: {last_error}") from last_error


def build_session(retries: int = 3) -> SessionLike:
    """Build an httpx-backed synchronous session with conservative retries."""

    return SyncHttpxSession(retries=retries)


def build_async_session(retries: int = 3) -> AsyncSessionLike:
    """Build an httpx-backed asynchronous session with conservative retries."""

    return AsyncHttpxSession(retries=retries)


def close_session(session: Any) -> None:
    close = getattr(session, "close", None)
    if callable(close):
        close()


async def aclose_session(session: Any) -> None:
    aclose = getattr(session, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(session, "close", None)
    if callable(close):
        close()


def iter_response_bytes(response: ResponseLike, *, chunk_size: int) -> Iterator[bytes]:
    iter_content = getattr(response, "iter_content", None)
    if callable(iter_content):
        yield from (chunk for chunk in iter_content(chunk_size=chunk_size) if chunk)
        return
    iter_bytes = getattr(response, "iter_bytes", None)
    if callable(iter_bytes):
        yield from (chunk for chunk in iter_bytes(chunk_size=chunk_size) if chunk)
        return
    content = bytes(response.content)
    if content:
        yield content


async def aiter_response_bytes(
    response: ResponseLike,
    *,
    chunk_size: int,
) -> AsyncIterator[bytes]:
    aiter_bytes = getattr(response, "aiter_bytes", None)
    if callable(aiter_bytes):
        async for chunk in aiter_bytes(chunk_size=chunk_size):
            if chunk:
                yield chunk
        return
    for chunk in iter_response_bytes(response, chunk_size=chunk_size):
        yield chunk


def close_response(response: ResponseLike) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


async def aclose_response(response: ResponseLike) -> None:
    aclose = getattr(response, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close_response(response)


def raise_for_http_error(response: ResponseLike, context: str) -> None:
    """Translate HTTP statuses into kraddr.geo domain exceptions."""

    status = int(response.status_code)
    if status < 400:
        return
    text = _text_preview(response)
    if status in {401, 403}:
        raise KrAddrAuthError(f"{context}: HTTP {status}: {text}")
    if status == 429:
        raise KrAddrRateLimitError(f"{context}: HTTP {status}: {text}")
    if 400 <= status < 500:
        raise KrAddrRequestError(f"{context}: HTTP {status}: {text}")
    if 500 <= status < 600:
        raise KrAddrServerError(f"{context}: HTTP {status}: {text}")


def response_json(response: ResponseLike, context: str) -> Mapping[str, Any]:
    """Return a decoded JSON object from a Juso-style response."""

    if response.encoding is None or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
        response.encoding = "utf-8"
    try:
        payload = response.json()
    except ValueError as exc:
        raise KrAddrParseError(f"{context}: response is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise KrAddrParseError(f"{context}: top-level JSON value is not an object")
    return payload


def without_none(params: Mapping[str, Any]) -> dict[str, Any]:
    """Return request parameters without keys whose value is None."""

    return {key: value for key, value in params.items() if value is not None}


def _backoff_seconds(attempt: int) -> float:
    return float(min(8.0, 0.3 * (2**attempt)))


def _text_preview(response: ResponseLike) -> str:
    try:
        return response.text[:300]
    except RuntimeError:
        return "<response body not read>"
