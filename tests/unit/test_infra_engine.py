from typing import Any

import orjson

from kraddr.geo.infra import engine as engine_module
from kraddr.geo.settings import Settings


def test_make_async_engine_passes_normalized_settings(monkeypatch) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    sentinel = object()

    def fake_create_async_engine(*args: Any, **kwargs: Any) -> object:
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)
    settings = Settings(
        pg_dsn="postgresql://u:p@localhost:5432/kraddr_geo",
        pg_pool_size=3,
        pg_max_overflow=2,
        pg_pool_recycle_s=77,
        pg_statement_timeout_ms=1234,
    )

    engine = engine_module.make_async_engine(settings)

    assert engine is sentinel
    assert calls[0][0] == ("postgresql+psycopg://u:p@localhost:5432/kraddr_geo",)
    assert calls[0][1]["pool_size"] == 3
    assert calls[0][1]["max_overflow"] == 2
    assert calls[0][1]["pool_pre_ping"] is True
    assert calls[0][1]["pool_recycle"] == 77
    assert calls[0][1]["connect_args"] == {"options": "-c statement_timeout=1234"}
    assert calls[0][1]["json_deserializer"] is orjson.loads
    assert calls[0][1]["json_serializer"]({"ok": True}) == '{"ok":true}'


def test_make_async_engine_allows_explicit_dsn_override(monkeypatch) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake_create_async_engine(*args: Any, **kwargs: Any) -> object:
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)

    engine_module.make_async_engine(Settings(), pg_dsn="postgresql+psycopg://override/db")

    assert calls[0][0] == ("postgresql+psycopg://override/db",)
