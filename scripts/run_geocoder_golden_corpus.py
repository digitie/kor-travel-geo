"""Run the T-140 geocoder/reverse golden corpus.

The default mode validates the static corpus schema only. ``--mode live`` uses
``AsyncAddressClient`` against a configured PostgreSQL database and checks the
expected status, result count, selected golden fields, and optional latency
budgets for each case.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from kortravelgeo.client import AsyncAddressClient

CORPUS_SCHEMA_VERSION = 1
DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "geocoder_golden_corpus.json"
)
DEFAULT_LIVE_EXCLUDE_TAGS = frozenset({"optional-source", "future-followup"})
Operation = Literal["geocode", "reverse", "search", "zipcode", "pobox"]


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    operation: Operation
    category: str
    description: str
    params: dict[str, Any]
    expected: dict[str, Any]
    tags: tuple[str, ...]
    source: str
    performance_budget_ms: float | None = None
    golden_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    operation: Operation
    category: str
    ok: bool
    skipped: bool
    elapsed_ms: float | None = None
    status: str | None = None
    result_count: int | None = None
    response_hash: str | None = None
    observed_fields: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoldenReport:
    schema_version: int
    mode: Literal["fixture", "live"]
    run_id: str
    started_at: str
    finished_at: str
    corpus_path: str
    corpus_sha256: str
    case_count: int
    selected_count: int
    skipped_count: int
    ok_count: int
    error_count: int
    categories: dict[str, int]
    operations: dict[str, int]
    results: tuple[CaseResult, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run T-140 geocoder golden corpus checks.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN for live mode. Defaults to settings.")
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to artifacts/golden-corpus/<run-id>.",
    )
    parser.add_argument(
        "--include-tag",
        action="append",
        default=None,
        help="Only include cases with this tag. May be passed multiple times.",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=None,
        help="Exclude cases with this tag. Defaults to optional live exclusions in live mode.",
    )
    parser.add_argument(
        "--include-default-skips",
        action="store_true",
        help="In live mode, include optional-source/future-followup cases too.",
    )
    return parser


def load_corpus(path: Path) -> tuple[GoldenCase, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"golden corpus root must be an object: {path}"
        raise ValueError(msg)
    if raw.get("schema_version") != CORPUS_SCHEMA_VERSION:
        msg = f"unsupported golden corpus schema_version: {raw.get('schema_version')!r}"
        raise ValueError(msg)
    items = raw.get("cases")
    if not isinstance(items, list):
        msg = f"golden corpus cases must be an array: {path}"
        raise ValueError(msg)
    cases = tuple(_case_from_mapping(item) for item in items)
    _validate_case_set(cases)
    return cases


def select_cases(
    cases: Sequence[GoldenCase],
    *,
    include_tags: Sequence[str] = (),
    exclude_tags: Sequence[str] = (),
) -> tuple[GoldenCase, ...]:
    include = set(include_tags)
    exclude = set(exclude_tags)
    selected: list[GoldenCase] = []
    for case in cases:
        tags = set(case.tags)
        if include and tags.isdisjoint(include):
            continue
        if exclude and not tags.isdisjoint(exclude):
            continue
        selected.append(case)
    return tuple(selected)


async def run_live_cases(
    cases: Sequence[GoldenCase],
    *,
    pg_dsn: str | None = None,
) -> tuple[CaseResult, ...]:
    results: list[CaseResult] = []
    async with AsyncAddressClient(pg_dsn=pg_dsn) as client:
        for case in cases:
            results.append(await _run_one_live_case(client, case))
    return tuple(results)


def fixture_results(cases: Sequence[GoldenCase]) -> tuple[CaseResult, ...]:
    return tuple(
        CaseResult(
            case_id=case.case_id,
            operation=case.operation,
            category=case.category,
            ok=True,
            skipped=False,
        )
        for case in cases
    )


def build_report(
    *,
    mode: Literal["fixture", "live"],
    run_id: str,
    started_at: str,
    corpus_path: Path,
    all_cases: Sequence[GoldenCase],
    selected_cases: Sequence[GoldenCase],
    results: Sequence[CaseResult],
) -> GoldenReport:
    finished_at = datetime.now(UTC).isoformat()
    skipped_count = (
        len(all_cases) - len(selected_cases) + sum(1 for item in results if item.skipped)
    )
    ok_count = sum(1 for item in results if item.ok and not item.skipped)
    error_count = sum(1 for item in results if not item.ok and not item.skipped)
    return GoldenReport(
        schema_version=CORPUS_SCHEMA_VERSION,
        mode=mode,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        corpus_path=str(corpus_path),
        corpus_sha256=_hash_file(corpus_path),
        case_count=len(all_cases),
        selected_count=len(selected_cases),
        skipped_count=skipped_count,
        ok_count=ok_count,
        error_count=error_count,
        categories=dict(sorted(Counter(case.category for case in all_cases).items())),
        operations=dict(sorted(Counter(case.operation for case in all_cases).items())),
        results=tuple(results),
    )


def write_report(report: GoldenReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "golden-report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(_summary_markdown(report), encoding="utf-8")


async def _run_one_live_case(client: AsyncAddressClient, case: GoldenCase) -> CaseResult:
    started = time.perf_counter()
    try:
        response = await _call_client(client, case)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        errors = _check_exception(case, exc)
        return CaseResult(
            case_id=case.case_id,
            operation=case.operation,
            category=case.category,
            ok=not errors,
            skipped=False,
            elapsed_ms=round(elapsed_ms, 3),
            status="ERROR",
            result_count=0,
            errors=tuple(errors),
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    payload = response.model_dump(mode="json", exclude_none=True)
    errors = _check_expected_payload(case, payload, elapsed_ms=elapsed_ms)
    return CaseResult(
        case_id=case.case_id,
        operation=case.operation,
        category=case.category,
        ok=not errors,
        skipped=False,
        elapsed_ms=round(elapsed_ms, 3),
        status=str(payload.get("status")),
        result_count=_result_count(payload),
        response_hash=_stable_response_hash(payload),
        observed_fields=_observed_fields(payload, case.golden_fields),
        errors=tuple(errors),
    )


async def _call_client(client: AsyncAddressClient, case: GoldenCase) -> Any:
    params = dict(case.params)
    if case.operation == "geocode":
        return await client.geocode(**params)
    if case.operation == "reverse":
        lon = float(params.pop("lon"))
        lat = float(params.pop("lat"))
        return await client.reverse(lon, lat, **params)
    if case.operation == "search":
        query = str(params.pop("query"))
        return await client.search(query, **params)
    if case.operation == "zipcode":
        point = params.get("point")
        if isinstance(point, list):
            params["point"] = (float(point[0]), float(point[1]))
        return await client.zipcode(**params)
    if case.operation == "pobox":
        return await client.pobox(**params)
    msg = f"unsupported operation: {case.operation}"
    raise ValueError(msg)


def _check_expected_payload(
    case: GoldenCase,
    payload: Mapping[str, Any],
    *,
    elapsed_ms: float,
) -> list[str]:
    expected = case.expected
    errors: list[str] = []
    expected_statuses = _expected_statuses(expected)
    actual_status = str(payload.get("status"))
    if expected_statuses and actual_status not in expected_statuses:
        errors.append(f"status {actual_status!r} not in {sorted(expected_statuses)!r}")

    min_results = expected.get("min_results")
    if min_results is not None and _result_count(payload) < int(min_results):
        errors.append(f"result_count {_result_count(payload)} < min_results {min_results}")

    max_results = expected.get("max_results")
    if max_results is not None and _result_count(payload) > int(max_results):
        errors.append(f"result_count {_result_count(payload)} > max_results {max_results}")

    for needle in _string_list(expected.get("contains_text")):
        if needle not in _payload_text(payload):
            errors.append(f"response does not contain {needle!r}")
    for needle in _string_list(expected.get("not_contains_text")):
        if needle in _payload_text(payload):
            errors.append(f"response unexpectedly contains {needle!r}")

    for path, value in _mapping(expected.get("fields")).items():
        actual = get_path(payload, path)
        if actual != value:
            errors.append(f"{path} expected {value!r}, got {actual!r}")

    for path, value in _mapping(expected.get("field_contains")).items():
        actual = get_path(payload, path)
        if actual is None or str(value) not in str(actual):
            errors.append(f"{path} does not contain {value!r}: {actual!r}")

    for path, value in _mapping(expected.get("numeric_lte")).items():
        actual = get_path(payload, path)
        if actual is None or float(actual) > float(value):
            errors.append(f"{path} expected <= {value!r}, got {actual!r}")

    for path, value in _mapping(expected.get("numeric_gte")).items():
        actual = get_path(payload, path)
        if actual is None or float(actual) < float(value):
            errors.append(f"{path} expected >= {value!r}, got {actual!r}")

    if case.performance_budget_ms is not None and elapsed_ms > case.performance_budget_ms:
        errors.append(
            f"elapsed_ms {elapsed_ms:.3f} exceeded budget {case.performance_budget_ms:.3f}"
        )
    return errors


def _check_exception(case: GoldenCase, exc: Exception) -> list[str]:
    expected = case.expected
    expected_statuses = _expected_statuses(expected)
    if "ERROR" not in expected_statuses:
        return [f"unexpected exception: {type(exc).__name__}: {exc}"]
    needle = expected.get("error_contains")
    if needle is not None and str(needle) not in str(exc):
        return [f"exception does not contain {needle!r}: {type(exc).__name__}: {exc}"]
    return []


def get_path(payload: Mapping[str, Any] | Sequence[Any], path: str) -> Any:
    current: Any = payload
    for raw_part in path.split("."):
        key, index = _split_path_part(raw_part)
        if key:
            if not isinstance(current, Mapping) or key not in current:
                return None
            current = current[key]
        if index is not None:
            if not isinstance(current, Sequence) or isinstance(current, str):
                return None
            if index >= len(current):
                return None
            current = current[index]
    return current


def _split_path_part(part: str) -> tuple[str, int | None]:
    if "[" not in part:
        return part, None
    key, _, rest = part.partition("[")
    if not rest.endswith("]"):
        msg = f"invalid path part: {part}"
        raise ValueError(msg)
    return key, int(rest[:-1])


def _case_from_mapping(item: object) -> GoldenCase:
    if not isinstance(item, dict):
        msg = f"golden corpus case must be an object: {item!r}"
        raise ValueError(msg)
    operation = str(item["operation"])
    if operation not in {"geocode", "reverse", "search", "zipcode", "pobox"}:
        msg = f"unsupported golden corpus operation: {operation}"
        raise ValueError(msg)
    return GoldenCase(
        case_id=str(item["case_id"]),
        operation=cast("Operation", operation),
        category=str(item["category"]),
        description=str(item["description"]),
        params=dict(cast("Mapping[str, Any]", item["params"])),
        expected=dict(cast("Mapping[str, Any]", item["expected"])),
        tags=tuple(str(tag) for tag in item.get("tags", ())),
        source=str(item["source"]),
        performance_budget_ms=(
            float(item["performance_budget_ms"])
            if item.get("performance_budget_ms") is not None
            else None
        ),
        golden_fields=tuple(str(path) for path in item.get("golden_fields", ())),
    )


def _validate_case_set(cases: Sequence[GoldenCase]) -> None:
    ids = [case.case_id for case in cases]
    duplicates = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        msg = f"duplicate golden corpus case_id: {duplicates}"
        raise ValueError(msg)
    for case in cases:
        if not case.case_id.startswith("T140-"):
            msg = f"case_id must start with T140-: {case.case_id}"
            raise ValueError(msg)
        if "status" not in case.expected and "status_any" not in case.expected:
            msg = f"case must declare expected.status or expected.status_any: {case.case_id}"
            raise ValueError(msg)


def _expected_statuses(expected: Mapping[str, Any]) -> set[str]:
    if "status_any" in expected:
        return set(_string_list(expected["status_any"]))
    if "status" in expected:
        return {str(expected["status"])}
    return set()


def _result_count(payload: Mapping[str, Any]) -> int:
    for key in ("candidates", "result"):
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str):
            return len(value)
    return 0


def _observed_fields(payload: Mapping[str, Any], paths: Sequence[str]) -> dict[str, Any]:
    return {path: get_path(payload, path) for path in paths}


def _stable_response_hash(payload: Mapping[str, Any]) -> str:
    normalized = _drop_unstable_fields(payload)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _drop_unstable_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _drop_unstable_fields(item)
            for key, item in sorted(value.items())
            if key not in {"query_id"}
        }
    if isinstance(value, list | tuple):
        return [_drop_unstable_fields(item) for item in value]
    return value


def _payload_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _mapping(value: object) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = f"expected mapping, got {type(value).__name__}"
        raise ValueError(msg)
    return value


def _string_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    msg = f"expected string or sequence, got {type(value).__name__}"
    raise ValueError(msg)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary_markdown(report: GoldenReport) -> str:
    lines = [
        f"# T-140 golden corpus run: {report.run_id}",
        "",
        "## 요약",
        "",
        f"- mode: `{report.mode}`",
        f"- corpus: `{report.corpus_path}`",
        f"- corpus sha256: `{report.corpus_sha256}`",
        f"- cases: `{report.case_count}`",
        f"- selected: `{report.selected_count}`",
        f"- skipped: `{report.skipped_count}`",
        f"- ok: `{report.ok_count}`",
        f"- errors: `{report.error_count}`",
        "",
        "## 실패",
        "",
    ]
    failures = [item for item in report.results if not item.ok and not item.skipped]
    if not failures:
        lines.append("- 없음.")
    else:
        for item in failures:
            lines.append(f"- `{item.case_id}`: {'; '.join(item.errors)}")
    return "\n".join(lines) + "\n"


async def _async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    run_id = args.run_id or datetime.now(UTC).strftime("t140-%Y%m%d-%H%M%S")
    started_at = datetime.now(UTC).isoformat()
    output_dir = args.output_dir or Path("artifacts") / "golden-corpus" / run_id
    cases = load_corpus(args.corpus)

    include_tags = tuple(args.include_tag or ())
    if args.exclude_tag is not None:
        exclude_tags = tuple(args.exclude_tag)
    elif args.mode == "live" and not args.include_default_skips:
        exclude_tags = tuple(sorted(DEFAULT_LIVE_EXCLUDE_TAGS))
    else:
        exclude_tags = ()
    selected = select_cases(cases, include_tags=include_tags, exclude_tags=exclude_tags)
    results = (
        await run_live_cases(selected, pg_dsn=args.pg_dsn)
        if args.mode == "live"
        else fixture_results(selected)
    )
    report = build_report(
        mode=cast("Literal['fixture', 'live']", args.mode),
        run_id=run_id,
        started_at=started_at,
        corpus_path=args.corpus,
        all_cases=cases,
        selected_cases=selected,
        results=results,
    )
    write_report(report, output_dir)
    print(_summary_markdown(report), end="")
    return 1 if report.error_count else 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
