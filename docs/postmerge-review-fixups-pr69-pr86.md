# PR #69~#86 post-merge 리뷰 audit/fixup

## 범위

- 확인 시각: 2026-05-29 KST
- 확인 대상: PR #69부터 PR #86까지
- 확인 표면:
  - `gh pr view <번호> --json comments,reviews,latestReviews`
  - GraphQL `reviewThreads(first:100)`의 `totalCount`, `isResolved`, `isOutdated`, `path`, `line`
- 결과:
  - 대상 PR은 모두 `MERGED`
  - conversation comment는 모두 0건
  - GraphQL review thread는 PR #69~#86 모두 0건
  - formal review는 PR #69~#75, #77~#82, #84에 존재했고 모두 본문을 다시 읽었다. PR #76, #83, #85, #86은 formal review 0건이었다.

## 반영 요약

| PR | 리뷰 핵심 | 반영 |
|----|-----------|------|
| #69 | v2 candidate schema의 `distance_m`, confidence, source enum 후속 | PR #76/#83 반영 상태를 재확인했다. `distance_m`/confidence/point precision은 v2 schema 고도화 후보로 유지한다. |
| #70 | T-053 표본 vs 전수 범위, lockfile URL, reason_code 통제 | PR #76/#83 반영 상태를 재확인했다. 전수 위반 export job은 T-053 후속 후보로 유지한다. |
| #71 | `mv_geocode_text_search` 운영 refresh 경고, storage/sizing | PR #76/#83 반영 상태를 재확인했다. helper MV size와 raw refresh 금지 경고가 문서에 남아 있다. |
| #72 | upload cleanup TOCTOU와 advisory lock | PR #82/T-059에서 CLI/Job advisory lock 표준화를 반영했다. |
| #73 | callback retry 멱등성과 secret 운영 가이드 | PR #76/#83 반영 상태를 재확인했다. receiver 예제와 secret require 정책은 후속 후보로 유지한다. |
| #74 | backup/restore size sampler hot-path 비용 | PR #76/#83 반영 상태를 재확인했다. sampler 캐시 보강이 반영됐다. |
| #75 | release hook gate/count와 ledger repair | PR #76/#83 반영 상태를 재확인했다. manual repair 자동화는 hot-swap 실행 표면 후속으로 유지한다. |
| #76 | PR #69~#75 follow-up PR | comment/review/thread 0건을 확인했다. |
| #77 | 수동 table stats capture lock 충돌을 `409 E0409`로 구분 | PR #81/#83 반영 상태를 재확인했다. |
| #78 | `replace_current` maintenance window gate audit | PR #81 리뷰에서 발견된 `actor_type="job"` CHECK 위반은 PR #83에서 `system`으로 고쳐져 있음을 확인했다. |
| #79 | 실제 PostgreSQL 제약 테스트 guard | PR #79 머지 전 반영 상태와 PR #83 재확인을 확인했다. |
| #80 | restore hot-swap plan edge case | PR #80 머지 전 후속 commit으로 alias timestamp, DB inventory, 긴 alias, maintenance DB 설정이 반영됐음을 확인했다. |
| #81 | `maintenance_window.authorize` audit bug | PR #83에서 수정 완료됨을 확인했다. |
| #82 | T-059 lock 충돌 동작, 미사용 wait, table kind 경합 | PR #82 머지 전 후속 commit과 PR #83 문서화를 확인했다. |
| #83 | PR #69~#82 follow-up PR | comment/review/thread 0건을 확인했다. |
| #84 | GeoIP gate middleware 순서, `testclient` 우회, open path prefix, XFF port/bracket 표기 | 이번 PR에서 GeoIP gate를 admission control보다 바깥에 설치하고, `testclient` 특별 허용을 제거했다. `X-Forwarded-For`의 `1.2.3.4:port`, `[IPv6]:port` 표기를 파싱하도록 보강했다. open path는 prefix 의미를 문서화했다. |
| #85 | T-055 N150/Odroid 준비 | comment/review/thread 0건을 확인했다. |
| #86 | T-027 최종 클린 재적재 | comment/review/thread 0건을 확인했다. |

## 코드 반영 상세

### PR #84 M1 — GeoIP gate를 admission control보다 먼저 실행

FastAPI/Starlette middleware는 나중에 추가된 middleware가 더 바깥에서 먼저 실행된다. 기존 `create_app()`은 `install_geoip_gate()` 뒤에 `_install_admission_control()`을 호출해 admission control이 먼저 semaphore를 잡을 수 있었다. 이번 PR에서 호출 순서를 바꿔 non-KR/denylist 요청이 admission capacity를 점유하기 전에 `403 E0403`으로 차단되게 했다.

회귀 테스트는 KR 요청 하나가 admission semaphore를 점유한 상태에서 US 요청을 보내도 `429`가 아니라 GeoIP `403`이 반환되는지 확인한다.

### PR #84 M2 — `testclient` production bypass 제거

`classify_ip()`의 `testclient` 호스트명 특별 허용을 제거했다. 테스트는 명시 client IP 또는 mock reader를 사용한다. 잘못된 client host는 항상 `invalid_client_ip`로 deny된다.

### PR #84 L3/L4 — open path prefix와 XFF 표기

`geoip_open_paths`는 exact path와 child prefix를 함께 연다는 정책을 문서화했다. 새 open path를 추가할 때 해당 prefix 아래 민감 route를 mount하지 않는 운영 제약을 명시했다.

또한 proxy가 `X-Forwarded-For`에 `1.2.3.4:5678` 또는 `[2001:4860:4860::8888]:443`처럼 port를 붙이는 경우에도 마지막 untrusted client IP를 정상 추출한다.

## 보류한 항목

- PR #69의 `CandidateV2.distance_m` first-class 필드와 confidence/precision schema 고도화는 v2 API 개선 후속으로 둔다.
- PR #70의 C1~C10 전수 위반 export job은 T-053 1차 범위를 넘으므로 후속으로 둔다.
- PR #73의 callback receiver 예제와 `(artifact_id,event)` 멱등성 문서는 outbound callback 수신 예제 PR에서 다룬다.
- PR #75의 release ledger repair 자동화는 restore hot-swap 실행 표면과 함께 다룬다.
- PR #82의 서로 다른 job kind가 같은 물리 table을 쓰는 cross-process 경합은 table 단위 공유 namespace 후속 후보로 둔다.
- PR #84의 deny 응답 envelope를 `error_payload()`로 통일하는 것은 사용자 메시지와 `client_country`/`reason` 노출 계약을 바꾸므로 이번 PR에서는 유지한다.

## 검증

- `ruff check src/kortravelgeo/api/app.py src/kortravelgeo/infra/geoip.py tests/unit/test_geoip_gate.py`
- `pytest tests/unit/test_geoip_gate.py tests/unit/test_api_admission_control.py tests/unit/test_api_app_contract.py -q` → `14 passed`
- `mypy --no-incremental src/kortravelgeo/api/app.py src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py`
