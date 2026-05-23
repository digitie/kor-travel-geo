"""Text/SHP consistency report SQL builders."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.dto.admin import ConsistencyCase, ConsistencyReport

CASE_SQL: dict[str, tuple[str, str]] = {
    "C1": (
        "텍스트에만 존재하는 BD_MGT_SN",
        """
SELECT count(*) AS count
  FROM tl_juso_text j
  LEFT JOIN tl_spbd_buld_polygon p ON p.bd_mgt_sn = j.bd_mgt_sn
 WHERE p.bd_mgt_sn IS NULL
""",
    ),
    "C2": (
        "SHP polygon에만 존재하는 BD_MGT_SN",
        """
SELECT count(*) AS count
  FROM tl_spbd_buld_polygon p
  LEFT JOIN tl_juso_text j ON j.bd_mgt_sn = p.bd_mgt_sn
 WHERE j.bd_mgt_sn IS NULL
""",
    ),
    "C3": (
        "대표 출입구가 해소되지 않은 건물",
        """
SELECT count(*) AS count
  FROM tl_juso_text j
  LEFT JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
 WHERE e.bd_mgt_sn IS NULL
""",
    ),
    "C9": (
        "PNU 형식 오류",
        """
SELECT count(*) AS count
  FROM tl_juso_text
 WHERE pnu IS NOT NULL
   AND (char_length(pnu) <> 19 OR substring(pnu from 11 for 1) NOT IN ('1','2'))
""",
    ),
}


async def run_case(engine: AsyncEngine, code: str) -> ConsistencyCase:
    name, sql = CASE_SQL[code]
    async with engine.connect() as conn:
        count = int(await conn.scalar(text(sql)) or 0)
    severity: Literal["OK", "INFO", "WARN", "ERROR"]
    if count == 0:
        severity = "OK"
    elif code in {"C2", "C9"}:
        severity = "ERROR"
    elif code in {"C1"}:
        severity = "WARN"
    else:
        severity = "INFO"
    return ConsistencyCase(code=code, name=name, severity=severity, count=count)


async def run_all_cases(
    engine: AsyncEngine,
    *,
    scope: str = "full",
    cases: tuple[str, ...] = ("C1", "C2", "C3", "C9"),
    generated_by: Literal["cli", "api", "cron"] = "api",
) -> ConsistencyReport:
    started_at = datetime.now(UTC)
    case_results = tuple([await run_case(engine, code) for code in cases])
    severity_max = _max_severity(case_results)
    report = ConsistencyReport(
        report_id=f"consistency_{uuid4().hex}",
        scope=scope,
        severity_max=severity_max,
        source_set={},
        started_at=started_at,
        finished_at=datetime.now(UTC),
        cases=case_results,
        generated_by=generated_by,
    )
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
INSERT INTO load_consistency_reports
  (report_id, scope, started_at, finished_at, source_set, cases, severity_max, generated_by)
VALUES
  (:report_id, :scope, :started_at, :finished_at, :source_set, :cases, :severity_max, :generated_by)
"""
            ),
            report.model_dump(mode="json"),
        )
    return report


def _max_severity(cases: tuple[ConsistencyCase, ...]) -> Literal["OK", "INFO", "WARN", "ERROR"]:
    order = {"OK": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
    reverse = {value: key for key, value in order.items()}
    return reverse[max(order[case.severity] for case in cases)]  # type: ignore[return-value]

