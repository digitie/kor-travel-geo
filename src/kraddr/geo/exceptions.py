"""Domain exceptions for kraddr.geo."""

from __future__ import annotations


class KraddrGeoError(Exception):
    """Base exception carrying a stable error code and HTTP status."""

    code = "E0000"
    http_status = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        http_status: int | None = None,
        hint: str | None = None,
    ) -> None:
        self.message = message or self.__class__.__name__
        self.code = code or self.code
        self.http_status = http_status or self.http_status
        self.hint = hint
        super().__init__(self.message)


class InvalidInputError(KraddrGeoError):
    code = "E0100"
    http_status = 400


class InvalidAddressError(InvalidInputError):
    code = "E0101"


class InvalidCoordinateError(InvalidInputError):
    code = "E0102"


class RateLimitError(KraddrGeoError):
    code = "E0200"
    http_status = 429


class NotFoundError(KraddrGeoError):
    code = "E0404"
    http_status = 404


class DatabaseError(KraddrGeoError):
    code = "E0500"
    http_status = 503


class ExternalApiError(KraddrGeoError):
    code = "E0501"
    http_status = 502


class LoaderError(KraddrGeoError):
    code = "E0502"
    http_status = 500


class ConfigError(KraddrGeoError):
    code = "E0503"
    http_status = 500
