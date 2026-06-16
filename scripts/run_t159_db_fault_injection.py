"""Run deterministic T-159 DB fault-injection checks without controlling PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (REPO_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from kortravelgeo.api.responses import register_exception_handlers  # noqa: E402
from kortravelgeo.api.routers import healthz  # noqa: E402
from kortravelgeo.settings import Settings, reset_settings, set_settings  # noqa: E402

T159_SCHEMA_VERSION = 1
Mode = Literal["ok", "down", "slow"]


@dataclass(frozen=True, slots=True)
class FaultCheck:
    name: str
    method: str
    path: str
    mode: Mode
    expected_http_status: int
    expected_ready: bool | None
    expected_error_type: str | None = None
    fast_fail: bool = False
    forbid_text: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FaultResult:
    name: str
    mode: Mode
    http_status: int | None
    elapsed_ms: float
    passed: bool
    ready: bool | None
    database_status: str | None
    error_type: str | None
    failure: str | None
    response_bytes: int


@dataclass(frozen=True, slots=True)
class FaultReport:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    git_commit: str | None
    git_branch: str | None
    python_version: str
    platform: str
    readiness_timeout_ms: int
    slow_delay_ms: int
    fast_fail_ms: int
    results: tuple[FaultResult, ...]


class _FakePool:
    def size(self) -> int:
        return 10

    def checkedin(self) -> int:
        return 10

    def checkedout(self) -> int:
        return 0

    def overflow(self) -> int:
        return 0


class _FakeSyncEngine:
    pool = _FakePool()


class _FakeResult:
    def mappings(self) -> _FakeResult:
        return self

    def one(self) -> dict[str, str]:
        return {"current_database": "kor_travel_geo", "postgres_version": "16.4"}


class _FakeConnection:
    def __init__(self, engine: _FakeEngine) -> None:
        self._engine = engine

    async def execute(self, _statement: object) -> _FakeResult:
        await self._engine.probe()
        return _FakeResult()


class _FakeConnectionContext:
    def __init__(self, engine: _FakeEngine) -> None:
        self._engine = engine

    async def __aenter__(self) -> _FakeConnection:
        return _FakeConnection(self._engine)

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeEngine:
    sync_engine = _FakeSyncEngine()

    def __init__(self, *, slow_delay_ms: int) -> None:
        self.mode: Mode = "ok"
        self.slow_delay_ms = slow_delay_ms

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self)

    async def probe(self) -> None:
        if self.mode == "slow":
            await asyncio.sleep(self.slow_delay_ms / 1_000)
            return
        if self.mode == "down":
            raise OperationalError(
                "SELECT private_fault_probe",
                {"token": "secret-token"},
                RuntimeError("simulated connection reset"),
            )


class _FakeClient:
    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the T-159 DB fault-injection harness.")
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to artifacts/chaos/<run-id>.",
    )
    parser.add_argument("--readiness-timeout-ms", type=int, default=25)
    parser.add_argument("--slow-delay-ms", type=int, default=500)
    parser.add_argument("--fast-fail-ms", type=int, default=250)
    return parser


def build_app(engine: _FakeEngine) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(healthz.router, prefix="/v1")
    app.state.client = _FakeClient(engine)

    @app.get("/v1/address/geocode")
    async def geocode() -> dict[str, object]:
        await engine.probe()
        return {"response": {"status": "OK", "result": []}}

    return app


def checks() -> tuple[FaultCheck, ...]:
    return (
        FaultCheck("baseline-readyz", "GET", "/v1/readyz", "ok", 200, True),
        FaultCheck(
            "disconnect-readyz",
            "GET",
            "/v1/readyz",
            "down",
            503,
            False,
            expected_error_type="OperationalError",
            fast_fail=True,
            forbid_text=("private_fault_probe", "secret-token"),
        ),
        FaultCheck(
            "disconnect-public-api",
            "GET",
            "/v1/address/geocode",
            "down",
            503,
            None,
            fast_fail=True,
            forbid_text=("private_fault_probe", "secret-token"),
        ),
        FaultCheck(
            "slow-io-readyz",
            "GET",
            "/v1/readyz",
            "slow",
            503,
            False,
            expected_error_type="TimeoutError",
            fast_fail=True,
        ),
        FaultCheck("recovered-readyz", "GET", "/v1/readyz", "ok", 200, True),
        FaultCheck("recovered-public-api", "GET", "/v1/address/geocode", "ok", 200, None),
    )


async def run_check(
    client: httpx.AsyncClient,
    engine: _FakeEngine,
    check: FaultCheck,
    *,
    fast_fail_ms: int,
) -> FaultResult:
    engine.mode = check.mode
    started = time.perf_counter()
    try:
        response = await client.request(check.method, check.path)
        elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
        payload = _json_body(response)
        ready = _ready_value(payload)
        database_status = _database_status(payload)
        error_type = _database_error_type(payload)
        failure = _failure(
            check,
            response=response,
            elapsed_ms=elapsed_ms,
            ready=ready,
            error_type=error_type,
            body=response.text,
            fast_fail_ms=fast_fail_ms,
        )
        return FaultResult(
            name=check.name,
            mode=check.mode,
            http_status=response.status_code,
            elapsed_ms=elapsed_ms,
            passed=failure is None,
            ready=ready,
            database_status=database_status,
            error_type=error_type,
            failure=failure,
            response_bytes=len(response.content),
        )
    except httpx.HTTPError as exc:
        return FaultResult(
            name=check.name,
            mode=check.mode,
            http_status=None,
            elapsed_ms=round((time.perf_counter() - started) * 1_000, 3),
            passed=False,
            ready=None,
            database_status=None,
            error_type=None,
            failure=str(exc),
            response_bytes=0,
        )


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _ready_value(payload: dict[str, Any]) -> bool | None:
    ready = payload.get("ready")
    return ready if isinstance(ready, bool) else None


def _database_status(payload: dict[str, Any]) -> str | None:
    database = _database_component(payload)
    status = database.get("status") if database is not None else None
    return status if isinstance(status, str) else None


def _database_error_type(payload: dict[str, Any]) -> str | None:
    database = _database_component(payload)
    error_type = database.get("error_type") if database is not None else None
    return error_type if isinstance(error_type, str) else None


def _database_component(payload: dict[str, Any]) -> dict[str, Any] | None:
    components = payload.get("components")
    if not isinstance(components, dict):
        return None
    database = components.get("database")
    return database if isinstance(database, dict) else None


def _failure(
    check: FaultCheck,
    *,
    response: httpx.Response,
    elapsed_ms: float,
    ready: bool | None,
    error_type: str | None,
    body: str,
    fast_fail_ms: int,
) -> str | None:
    if response.status_code != check.expected_http_status:
        return f"http {response.status_code}, expected {check.expected_http_status}"
    if check.expected_ready is not None and ready != check.expected_ready:
        return f"ready {ready}, expected {check.expected_ready}"
    if check.expected_error_type is not None and error_type != check.expected_error_type:
        return f"error_type {error_type}, expected {check.expected_error_type}"
    if check.fast_fail and elapsed_ms > fast_fail_ms:
        return f"elapsed_ms {elapsed_ms} exceeded fast_fail_ms {fast_fail_ms}"
    leaked = [text for text in check.forbid_text if text in body]
    if leaked:
        return f"response leaked forbidden text: {', '.join(leaked)}"
    return None


def write_summary_markdown(report: FaultReport, output_path: Path) -> None:
    lines = [
        f"# T-159 DB fault injection: {report.run_id}",
        "",
        "## 실행 환경",
        "",
        f"- 시작: `{report.started_at}`",
        f"- 종료: `{report.finished_at}`",
        f"- Git: `{report.git_branch}` / `{report.git_commit}`",
        f"- Python: `{report.python_version}`",
        f"- Platform: `{report.platform}`",
        f"- Readiness timeout: `{report.readiness_timeout_ms}ms`",
        f"- Slow delay: `{report.slow_delay_ms}ms`",
        f"- Fast-fail budget: `{report.fast_fail_ms}ms`",
        "",
        "## 결과",
        "",
        "| check | mode | http | ready | db status | error | elapsed ms | pass |",
        "|-------|------|-----:|-------|-----------|-------|-----------:|------|",
    ]
    for row in report.results:
        lines.append(
            f"| `{row.name}` | `{row.mode}` | {_md_value(row.http_status)} | "
            f"{_md_value(row.ready)} | `{row.database_status or 'n/a'}` | "
            f"`{row.error_type or 'n/a'}` | {row.elapsed_ms:.3f} | "
            f"{'yes' if row.passed else 'no'} |"
        )
    failures = [row for row in report.results if not row.passed]
    if failures:
        lines.extend(["", "## 실패", ""])
        for row in failures:
            lines.append(f"- `{row.name}`: {row.failure}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_value(value: object) -> str:
    return "n/a" if value is None else str(value)


def _git_output(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", *args),
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _run_id() -> str:
    return datetime.now(UTC).strftime("t159-db-fault-%Y%m%d-%H%M%S")


async def _amain(args: argparse.Namespace) -> int:
    if args.readiness_timeout_ms < 1:
        msg = "--readiness-timeout-ms must be at least 1"
        raise ValueError(msg)
    if args.slow_delay_ms <= args.readiness_timeout_ms:
        msg = "--slow-delay-ms must be greater than --readiness-timeout-ms"
        raise ValueError(msg)
    if args.fast_fail_ms <= args.readiness_timeout_ms:
        msg = "--fast-fail-ms must be greater than --readiness-timeout-ms"
        raise ValueError(msg)

    run_id = args.run_id or _run_id()
    output_dir = args.output_dir or Path("artifacts") / "chaos" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = _FakeEngine(slow_delay_ms=args.slow_delay_ms)
    app = build_app(engine)
    set_settings(Settings(api_readiness_timeout_ms=args.readiness_timeout_ms))
    started_at = datetime.now(UTC).isoformat()
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            result_items: list[FaultResult] = []
            for check in checks():
                result_items.append(
                    await run_check(client, engine, check, fast_fail_ms=args.fast_fail_ms)
                )
            results = tuple(result_items)
    finally:
        reset_settings()

    report = FaultReport(
        schema_version=T159_SCHEMA_VERSION,
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        git_commit=_git_output("rev-parse", "HEAD"),
        git_branch=_git_output("branch", "--show-current"),
        python_version=platform.python_version(),
        platform=platform.platform(),
        readiness_timeout_ms=args.readiness_timeout_ms,
        slow_delay_ms=args.slow_delay_ms,
        fast_fail_ms=args.fast_fail_ms,
        results=results,
    )
    (output_dir / "fault-report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_summary_markdown(report, output_dir / "summary.md")
    print(output_dir)
    return 0 if all(row.passed for row in results) else 1


def main() -> None:
    raise SystemExit(asyncio.run(_amain(build_parser().parse_args())))


if __name__ == "__main__":
    main()
