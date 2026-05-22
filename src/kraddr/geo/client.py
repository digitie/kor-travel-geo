"""Async library client entry point."""

from __future__ import annotations

from typing import Any, Self

from .settings import Settings, get_settings


class AsyncAddressClient:
    """Async-only client facade for address geocoding operations."""

    def __init__(self, settings: Settings | None = None, *, pg_dsn: str | None = None) -> None:
        self.settings = settings or get_settings()
        if pg_dsn is not None:
            self.settings = self.settings.model_copy(update={"pg_dsn": pg_dsn})
        self.closed = True

    async def __aenter__(self) -> Self:
        self.closed = False
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        self.closed = True

    async def geocode(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("geocode is planned in T-011.")

    async def reverse_geocode(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("reverse_geocode is planned in T-016.")

    async def search(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("search is planned in T-016.")

    async def zipcode(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("zipcode is planned in T-016.")

    async def pobox(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("pobox is planned in T-016.")
