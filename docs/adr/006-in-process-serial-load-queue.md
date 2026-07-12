# ADR-006: 적재 작업은 단일 백엔드 인스턴스의 in-process 큐로 직렬 처리한다

- 상태: superseded by ADR-066
- 날짜: 2026-05-22
- 결정자: human

> **T-290k(ADR-066) 갱신**: in-process `asyncio.Queue`+`Semaphore(1)` 직렬 큐(drain)는 완전히 은퇴했다.
> 적재/백업/복원/full-load는 Dagster op으로 실행하고(`kortravelgeo_dagster`), 자원 직렬화는 Dagster
> 단일 run + 기존 cross-process advisory lock으로 대체한다. `load_jobs` 테이블(ADR-011)은 실행 상태
> 원장으로 유지된다.

## 컨텍스트
관리 UI가 적재를 트리거할 때 HTTP 요청이 길어지고 진행률을 폴링할 방법이 필요하다. 동시에 여러 시도를 병렬 적재하면 ARM 8GB 환경에서 `work_mem`/IOPS가 한꺼번에 고갈된다.

## 결정
`api/_jobs.py`에 `asyncio.Queue` + `Semaphore(1)` 기반 in-process 큐를 둔다. 단일 백엔드 인스턴스 가정. 다중 인스턴스가 필요해지면 Redis(RQ) 또는 PostgreSQL `LISTEN`/`NOTIFY`로 같은 인터페이스 유지하며 확장한다.

## 근거
- 동시 실행 1개 → 자원 고갈 방지
- 진행률·취소·log_tail이 단일 프로세스 메모리에 자연스럽게 살아 있음
- 외부 큐 시스템 도입 비용 회피

## 결과(긍정)
- 운영 단순. 작업 상태가 즉시 보임
- 사용자가 화면을 닫아도 적재는 끝까지 진행

## 결과(부정)
- 프로세스 재시작 시 진행 중 작업 손실 → 매니페스트 기반 재개 필요
- 다중 인스턴스 배포 불가(향후 ADR로 재검토)
