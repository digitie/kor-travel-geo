# Geo579 이미지 점검·stdlib bytecode 최종 리뷰 정산

## 판정과 불변 범위

SOURCE_PASS. 최종 제품·규범 기준은7ba3dd1df24dfde9ed6c16fe70b52badc72d78d9이며
[초안 PR579](https://github.com/digitie/kor-travel-geo/pull/579)의 Geo578 위 후속이다.
제품·테스트·의존성·Dockerfile은 최초a316c340bd9ecec3d0eb0907f74dc830cbd8c0d2와 동일하고,
98c048/7ba3dd1의 변경은 활성화 필수 전제와 역사 비교시점 문서 정정뿐이다.
이 closure는 독립 원문6개의 byte 보존·통합 판정·색인만 추가하며 제품/규범을 바꾸지 않는다.
저자 D의 검사와 Common36 저술을 새 독립 제품 리뷰로 집계하지 않는다.

A는 선행577/578/579와 관련 경로를 FULL로 읽었다. C는 본인577 저술을 독립 승인으로
세지 않고579 FULL10과 연결 경로·두 문서 delta를 독립 검토했다. 둘은 상대 원문을 읽지 않았고
최종 원문은 각자가 고정한 뒤 통합했다. 최종 열린 P0/P1/P2/P3는0이다.

| finding | 최초 상태 | 정산 |
| --- | --- | --- |
| GEO-A-P2-01 native 복구 활성화 필수 배포 전제 누락 | a316 stack CHANGES_REQUIRED | 98c048에서 exact origin 독점·overlap 금지·구 PID/startticks/worker/cgroup 물리 소멸·UNKNOWN STOPPED·고정 Common §15 링크 추가, A/C 재검 PASS |
| GEO579-C-DOC-01 현재 pin/byte동일 비교 시점 혼동 | 98c048 P3 OPEN | 7ba3dd1에서 현재344/API core-only와 역사73e→ad988 비교를 분리, C FIXED·A 최종 PASS |

최초 CHANGES_REQUIRED/P3 OPEN을 지우거나 과거 commit을 소급 PASS로 바꾸지 않는다.
Geo577/578 단독 중간 commit의 활성화를 이 통합 source PASS로 승인하지 않는다.
소비자 활성화는 [적용 안내](../common-grpc-health-adoption.md)의 독점/물리 소멸 전제를 따른다.

## 원문·SHA256

원문 내용·판정·실행 숫자는 변경 없이 복사했다.

| 원문 | SHA256 |
| --- | --- |
| [2026-10-16-image-health-a-initial.md](evidence/2026-10-16-image-health-a-initial.md) | ccccb11f5e65ad2cddc136bc55d12a65e49ecdde6f3f292b417f6c7356bb8ce6 |
| [2026-10-16-image-health-a-postfix.md](evidence/2026-10-16-image-health-a-postfix.md) | a848cd272130d919bb9d2d69a98deaf3b485b97c9bbf131c68c77d2cb0c10b03 |
| [2026-10-16-image-health-a-final.md](evidence/2026-10-16-image-health-a-final.md) | 2d064e2f2fac13925492cdcbcd47532a1bacc3e046d5e15df8dbcdb5c5e775d3 |
| [2026-10-16-image-health-c-initial.md](evidence/2026-10-16-image-health-c-initial.md) | ce3624bb6375f0f95ff265a35068217fb06ddf9a62854c2d348c7bf23023b7c9 |
| [2026-10-16-image-health-c-postfix.md](evidence/2026-10-16-image-health-c-postfix.md) | f530fd8125b9ba7d0cf04b5f826cefee77e7105e17efc153e8b1ad24a2c89718 |
| [2026-10-16-image-health-c-final.md](evidence/2026-10-16-image-health-c-final.md) | 01fbb376baba1ed97b5a9c6127287c23924a543ff0429b69233108778bcdb096 |

## 검증의 실제 범위

저자: 최초 계약5FAIL→최종 신규8PASS, Python1915PASS/141SKIP/187warnings,
Dagster148PASS/10warnings, 실제 설치 wheel 집중16PASS, Ruff/mypy168파일/
계층167파일·612의존성·계약1/OpenAPI PASS. DB 실제 DSN 미제공 skip은 통과가 아니다.
순수 wheel source·metadata·RECORD 검사와 대역 명령은 Docker build의 대체가 아니다.

A: 자체 immutable archive35회귀·inert21조건, compile RUN 제거 mutant1FAIL/1PASS,
기존 로컬 wheel2의 source/RECORD/METADATA 직접 검증.
C: 자체 archive16PASS, 구578에서 신규8회귀5FAIL/3PASS.
각 작성자/리뷰어 숫자를 서로 중복 합산하지 않는다. 세부 실패와 실행 경계는 위 원문에 둔다.
최종7ba3dd1 CI backend/openapi/integration-postgis/dagster/frontend5개 SUCCESS를
읽기 확인했다. closure 이후 새 HEAD CI는 별도로 확인해야 한다.

## 외부 gate

Common37 및 Geo 선행 stack과579를 머지한 뒤 **머지된 source**로 이미지/context를 준비한다.
Dockerfile의 API 기본HC보다 실제 Compose override가 우선한다.
기존 urllib 본문/redirect와 새 Common header-only2xx는 다른 의미이며 준비 조회와 별개다.
원 CS 복구/상태조회/튜닝·스케줄·UI를 유지한다. [이미지 안내](../runbooks/image-health-bytecode.md)를 따른다.
실제 최종 interpreter pyc/source/magic/권한·원 metadata·Config/RootFS/의존성·운영 적용 및
동일 부하 CPU/RSS·live API/UI 검증은 아직 NOT_RUN이다.
root의 기존 Geo-only UI/latency baseline은579 배포 효과로 집계하지 않는다.
