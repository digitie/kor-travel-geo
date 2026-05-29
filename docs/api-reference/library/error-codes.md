# 오류 코드

이 문서는 API와 `AsyncAddressClient`가 공유하는 도메인 오류 코드를 요약한다. REST 응답은 vworld 호환 구조를 유지하므로 오류도 최상위 `response` 아래에 들어간다.

```json
{
  "response": {
    "status": "ERROR",
    "errorCode": "E0409",
    "errorMessage": "MV_REFRESH is already running for resource 00000000",
    "hint": "기존 작업이 끝난 뒤 다시 시도하세요."
  }
}
```

| 코드 | HTTP | 의미 | 대표 상황 |
|------|------|------|-----------|
| `E0100` | 400 | 잘못된 입력 | 필수 요청값 누락, 잘못된 요청 자료형 |
| `E0101` | 400 | 잘못된 주소 | 주소 문자열이 비어 있거나 정규화할 수 없음 |
| `E0102` | 400 | 잘못된 좌표 | `(lon, lat)`가 한국 영역 밖이거나 좌표 순서가 틀림 |
| `E0200` | 429 | rate limit | admission control 또는 외부 provider quota 보호 |
| `E0404` | 404 | 찾을 수 없음 | 대상 주소, job, artifact, report 없음 |
| `E0409` | 409 | 동시 실행 충돌 | T-059 이후 같은 advisory lock key의 CLI/API 운영 작업이 이미 실행 중 |
| `E0500` | 503 | DB 오류 | PostgreSQL 연결/쿼리 실패 |
| `E0501` | 502 | 외부 API 오류 | vworld/juso fallback 호출 실패 |
| `E0502` | 500 | 로더 오류 | 원천 파일 파싱, 적재, 후처리 실패 |
| `E0503` | 500 | 설정 오류 | 필수 환경변수 또는 provider 설정 오류 |

`E0409`는 "성공했지만 0건 처리"와 구분해야 한다. 운영자는 기존 작업이 끝난 뒤 같은 요청을 다시 보내거나, `/v1/admin/jobs`와 `/v1/admin/loads`에서 진행 중인 작업을 먼저 확인한다.
