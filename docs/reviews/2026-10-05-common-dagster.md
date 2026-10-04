# 공통 Dagster 복구·운영 UI 채택 최종 판정

- 최종 코드 verdict: PASS. 두 독립 reviewer PASS, 열린 finding0·DEFERRED0.
- 제품 `4c59efe3a778fb160b7d0a4fde2ca08967bf1531`, base `3f4ddc2dac3f31634a23ef0e9592f419e29e7d14`.
- Python common 고정 `73e3ff8b9398e533806d2d1a8435292570169de3`, UI/tokens source426de4f의 vendor/provenance와 lock integrity를 유지한다.
- [A UI·소비자 계약 최종 원문](evidence/2026-10-05-geo-final-evidence-ui.md),
  [B 복구·정합·예산 최종 원문](evidence/2026-10-05-geo-final-evidence-recovery.md).
  각 원문에 실행 ID·시각·immutable 격리·실행/미실행을 보존하고 서로 결과를 공개하지 않았다.
- [최초·수정·최종 원문 SHA256](evidence/2026-10-05-geo-common-originals.json).

## Finding 반영

| Finding | 반영·재검증 | 상태 |
|---|---|---|
| B-G-P1-01: 느린 첫 row가 이력 순회를 막음 | timeout row도 keyset checkpoint, 활성/과거100행 교대 및 유한 순회 | FIXED |
| B-G-P1-02: transient 취소 조회가 영구 실패/정상 leaf를 실패로 변경 | 관측 오류를 다음 poll에서 확인하고 leaf 완료·취소를 분리 | FIXED |
| B-G-P1-03: 실제 child crash에서 공통 fallback 요청0 | 실제 child crash 분류·부분/완료 checkpoint·native 중복 방지를 common에 구현 | FIXED·두 최종 common PASS |
| repository URL P2·접힌 모바일 메뉴 접근명 P3 | repository/location을 함께 encode·모바일은 그룹 이름 유지 | FIXED |
| B-G-P1-04: 늦은 child가 MV·release 게시 | child/root running·owner FOR UPDATE, 실제 교체/활성화 및 commit 전 guard | FIXED·실제 PostgreSQL swap/rollback |
| G-PUB-P2-01 / B-P2-01: MV 후 radius parts 별도 transaction 무검증 | swap/concurrent 모두 guard 전달, 긴 TRUNCATE/INSERT 후 commit 전 검사 | FIXED·실제 취소 rollback17건 중2건 |
| common C-PHASE-P1-01/B-P1-01/C-MERGE-P2-01 및 pin 전파 | 최종73e3ff8의 최신 RUN/STEP 증거·추가 IO 전 checkpoint·늦은 child 재개 | FIXED·두 독립 최종 PASS |

이전 원문 severity·BLOCK/CONDITIONAL을 지우거나 낮추지 않는다. root 통합 결과는 새로운 closure다.

## 실행한 gate와 실제 경계

- WSL/ext4 ruff·mypy166 files·lint-imports PASS. pytest1787 PASS/111 SKIP; focused153 PASS.
  111 SKIP을 PASS로 세지 않는다. 그중17개의 실제 SQL 경계는 기존 PostgreSQL 독립 UUID schema에서 별도로17 PASS.
- [기존 PostgreSQL 결과](evidence/2026-10-05-owned-postgres.log): 실제 owner/lease CAS와 MV swap 및
  radius parts TRUNCATE/INSERT rollback. radius fixture는 geometry SQL 대신 transaction 게시 경계를 검증한다.
  DB/PostGIS/RustFS 서비스 lifecycle 변경 없음.
- UI lint/type/build·231 tests PASS. React Doctor90점이며 기존 진단은 해결됐다고 주장하지 않는다.
- Linux n150 native Next build, 실제 읽기 전용 API·Dagster·PostgreSQL, Chromium·Firefox 각각13항목 PASS, pageerror0.
  [브라우저 결과](evidence/2026-10-05-geo-live-results.json), [desktop](evidence/2026-10-05-geo-live-chromium-desktop.png),
  [Firefox](evidence/2026-10-05-geo-live-firefox-desktop.png), [mobile](evidence/2026-10-05-geo-live-chromium-mobile.png).
  실제 API 중단/복구는 작업이 소유한 테스트 API만 사용했다. 운영 Dagster/DB를 중단하지 않았다.
- UI product는 ce82/596/4c59 사이에 동일하다. 후속 변경은 Python pin·ADR·metadata이고 UI build를 새 산출물로 재발행하지 않았다.
- 원래 CodeGraph MCP의 NTFS index 오류는 ext4 CLI sync/status/context로 대체하여 UI 영향 범위를 확인했다. 다른 checkout DB는 건드리지 않았다.
- `/security-review` 기본 headless 실행은0-turn으로 실제 검토가 없어서 PASS로 세지 않았다.
  공식 Anthropic 커스터마이즈 명령 템플릿을 실제 Read/Glob/Grep 환경·고정 diff에 맞춰 적용했고 최종14turn 정적 검토에서 보고 대상 HIGH/MEDIUM0이다.
  [정적 원문](evidence/2026-10-05-geo-security-final-result.md), [방법·raw digest](evidence/2026-10-05-geo-security-final-metadata.json).
  정적 감사는 runtime·live·tarball 실행 검증과 다르다.
- 제품 앞 단계596b7d1 CI backend/dagster/frontend/openapi PASS.
  [PR570](https://github.com/digitie/kor-travel-geo/pull/570)의4c59 및 문서 closure를 포함한 최종 head도 all checks PASS 후 merge한다.

## 미실행·후속·롤백

운영 daemon/queue 설정 전환·운영 worker kill·전체 provider/geometry 재적재·RSS 실측은 NOT_RUN.
운영 code-server의 기존 정의로 UI를 조회했으며 새 retry sensor 배포 완료로 표시하지 않는다.
50행 DOM·4MiB 응답·100행 순회·step 동시성1이 구조적 상한이며 실제 RSS 감소율 보장이 아니다.
이미 commit된 원천 적재·MV transaction은 이후 단계 취소 시에도 남는다. 전체 batch 원자성은 추가하지 않았다.

[ADR-068](../adr/068-common-dagster-recovery-and-ui.md),
[공통 구현 가이드](https://github.com/digitie/kor-travel-common/blob/main/docs/runbooks/dagster-adoption.md),
[common PR26](https://github.com/digitie/kor-travel-common/pull/26)를 따른다.
rollback은 이 PR merge를 revert하거나 이전 immutable Python/UI pin을 복원한다. API DTO/schema migration 변경 없음.
이 closure는 제품을 바꾸지 않고 원문·disposition·검증 증거·index와 현재 기록만 보존한다.

## 원문 bytes와 Git 표시본

[Canonical 원문 JSON](evidence/2026-10-05-review-originals.json)은 reviewer가 저장한 UTF-8/BOM/CRLF·말단 공백·빈 줄까지 그대로 보존한다. Git 공백 검증과 text 변환 때문에 Markdown 표시본만 LF·말단 공백/빈 줄을 정규화했다. finding·severity·verdict·본문 내용은 바꾸지 않았다. JSON의 sha256은 JSON raw_utf8를 UTF-8로 encode한 원본 bytes, display_sha256은 표시본 hash다. 모든 JSON 복원 원본의 hash를 생성 후 재확인했다. 원본을 수정한 것으로 오해하지 않도록 이 차이를 명시한다.
