<!-- SPDX-License-Identifier: GPL-3.0-only -->

# Geo 공용 UI 적용 최종 후보 — 독립 적대 리뷰 원본

- 실행 ID: GEO-UI-A-20261005-c3011220
- 리뷰어: James (/root/review_ui), 소비자 UI·인증·관측 계약 관점.
- 관측 시각: 2026-10-04 22:07:17~22:10:58 UTC (2026-10-05 07:07:17~07:10:58 KST).
- 저장소: F:/dev/kor-travel-geo-codex-dagster-common.
- base: 3f4ddc2dac3f31634a23ef0e9592f419e29e7d14.
- 실제 고정 candidate: c3011220e26e2a733260f429222eeebdcc459680 (Git rev-parse 확인).
- 공통 UI: 426de4fbad35282bb558712d922c06268e9aba62, dev.3 tarball SHA256 03feae21b9e44041b648ba6d0defc3b16b97973ed3c7e70a83b91d279afb2f43 직접 확인.
- 공통 Python pin: 92ebfa60ef976d830c08b353de633103650175ad.

## 격리와 범위

WSL Ubuntu-26.04 Git show/diff/archive의 고정 객체로 제품 소스·테스트를 검토했다. 상대 리뷰, 통합 판정, journal/closure는 읽지 않았다. 원본 저장소, 부모 mirror, 의존성, 설치, DB·컨테이너를 변경하지 않았다. 자체 snapshot /tmp/james-geo-final-c3011220에서 기존 ext4 node_modules와 Python venv를 읽기만 재사용했다. 추가 공격 파일·캐시는 자체 /tmp에만 기록했다. 첫 Vitest 설정의 닫는 괄호 오류는 자체 harness 오류이며 수정 후 실행했다.

전체 base→candidate의 UI/스타일/토큰/Node22 vendor Docker/공개 DTO 적용을 기존 독립 리뷰 맥락에서 다시 확인하고, 9db3918→candidate의 인증 경로 검증·조회 timeout·tick 조회·child fence·reconciler cursor 변경을 검토했다.

## 수행 검증 (EXECUTED)

1. 실제 고정 Geo component와 vendor UI를 jsdom에서 렌더링: 제품 기존 30건 + 자체 공격 11건 + 실제 LoginPage 비동기 SSR 함수 경로 공격 9건, 중복 제외 50건 PASS.
2. 자체 공격: named repository/location 공백 스케줄 URL, 미확인 schedule job·실패 tick·job runtime 상한, 의미적 unavailable 응답 시 마지막 snapshot 유지, 사용자가 선택한 두 번째 run과 그 상세 유지, unmount AbortSignal, 503/429/403/401 문구·password 초기화·공백 password 보존, 동시 제출 1회·내부 오류 미노출, 문서 링크 ref/aria-current/anchor props, 모바일 collapsed preference 이후 그룹 제목.
3. 실제 server sanitizeLocalPath를 사용한 LoginPage에서 인증 성공 분기만 모의했다. /%09/evil.example, 실제 탭, 이중 인코딩 탭, //evil.example, 단일·이중 인코딩 역슬래시는 기본 로컬 경로로만 redirect; 정상 로컬 query/hash와 인코딩 로컬 경로는 유지했다. 실제 쿠키/서명/fingerprint/폐기와 rate/origin 단위 검증은 제품 auth/session/proxy 테스트에 포함되어 통과했다.
4. 자체 archive의 tests/unit/test_dagster_router.py, test_dagster_reconciler.py, test_batch_dag.py: 51 PASS, 4.67초. ASGI·MockTransport를 사용해 외부 provider/PG 접근 없이 검증했다. activeRuns scope/merge·상한, 다른 origin 상세 비공개, 실패 확인, 4MiB 제한, 느린 chunk 전체 deadline, UNKNOWN 회수 보류·checkpoint 회귀를 포함한다.
5. 공통 Python 92eb는 별도 본인 독립 실행: child crash 7건 + recovery 56건 PASS 및 실제 10초 deadline liveness 공격으로 C-CHILD-P1-01을 재현했다. 상세 원문은 common-child-postfix-ui.md에 변경 없이 보존했다.

재현 명령:

```bash
cd /tmp/james-geo-final-c3011220/kor-travel-geo-ui
node /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/kor-travel-geo-ui/node_modules/vitest/vitest.mjs run --config /tmp/james-geo-final-c3011220/james.vitest.config.mjs --configLoader native tests/unit/james.integration-attack.test.tsx tests/unit/james.ssr-attack.test.tsx tests/unit/dagster-panel.test.tsx tests/unit/app-shell-drawer.test.tsx tests/unit/auth.test.ts tests/unit/session-revocation.test.ts tests/unit/proxy-gate.test.ts tests/unit/backup-workflow.test.ts

cd /tmp/james-geo-final-c3011220
PYTHONPATH=/tmp/james-geo-final-c3011220/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_GEOIP_GATE_MODE=off /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python -m pytest -q tests/unit/test_dagster_router.py tests/unit/test_dagster_reconciler.py tests/unit/test_batch_dag.py --confcutdir=/tmp/james-geo-final-c3011220/tests/unit
```

공격 원문 SHA256:
- tests/unit/james.integration-attack.test.tsx: f5d0369a88c25830bdc795bc4b510850246943ab4aa2315e9656a96475cae165.
- tests/unit/james.ssr-attack.test.tsx: 7c7b6d3d2f8910c5321c70144bbaaffbd443832634296570731a9918f8f133fd.

## 기존 본인 지적 disposition

- G-UI-P2-01 (P2) CLOSED: DagsterPanel.tsx:112가 named repository를 location 식별자에 포함한다. URL의 %40은 route segment를 decode하면 repo@geo location이므로 separator를 포함한 같은 경로이다. 기본 __repository__ 분기도 보존한다. 기존 공격 조건에서 링크 경로 검증 PASS. 실제 Dagster 브라우저 라우트 방문은 NOT_RUN.
- G-UI-P3-01 (P3) CLOSED: AppShell.tsx:319가 그룹 제목을 항상 제공하며 CSS는 desktop breakpoint에서만 숨긴다. collapsed localStorage가 있는 모바일 drawer의 조회·진단 제목 공격 PASS. severity를 낮추거나 원문을 변경하지 않았다.

## 남은 차단 finding

### G-UI-P1-02 — 느린 실패 이벤트 이력에서 공통 복구가 영구 진행하지 않는 pin (P1)

- 위치: kor-travel-geo-dagster/pyproject.toml:22; kor-travel-geo-dagster/src/kortravelgeo_dagster/definitions.py:97.
- 근본 위치: 공통 92eb packages/py/kor-travel-common/src/kortravelcommon/dagster.py:211-238,337-343 (본인 C-CHILD-P1-01).
- 시나리오: native retry를 쓰지 않는 fallback 운영에서 eligible backup_verify run의 STEP_FAILURE 이력 두 페이지가 각각 정상적으로 5.1초에 반환한다. RUN_EXCEPTION/DagsterSubprocessError와 101개의 FRAMEWORK_ERROR/ChildProcessCrashException/user_failure_data=None은 안전 판별 조건을 모두 만족한다.
- 재현: /tmp/james-common-child-92ebfa60/slow_pages_probe.py. 실제 SensorDefinition.evaluate_tick을 실제 10초 deadline으로 두 번 실행하여 각 10.0초 timeout, cursor 미진전, 이전 실패 미검사, 반환 child 0을 확인했다. 늦은 worker는 parent pending=true/native max_retries=0을 기록하지만 호출자가 종료되어 요청이 폐기된다. 모든 worker 종료를 확인한 뒤 instance를 닫았다.
- 영향: 이 Geo 후보가 해당 공통 factory를 실제 등록하고 92eb를 고정한다. 정상이나 지속적으로 느린 메타데이터에서 자동 복구와 뒤의 실패 선택이 진행하지 않아 사용자 목표인 영구 정지 방지에 위배된다. 동일 저장소에서 Geo daemon을 직접 실행한 결과라고 주장하지 않는다.
- 최소 수정/폐쇄 조건: 공통에서 per-run 페이지 progress를 안전하게 checkpoint/resume하거나 과다 예산 이력을 격리해 뒤의 실패가 진행하도록 보강하고, 부분 이력에서 provider/mixed 오류를 승인하지 않는 회귀를 유지한다. 실제 반복 tick 진행 회귀가 통과한 새 공통 SHA로 Geo pin을 갱신해야 한다.

Geo UI 자체의 새 P0/P1/P2 결함은 발견하지 않았다. 위 항목은 본인이 직접 검증한 공통 dependency 결함의 소비자 적용이며 상대 보고서를 합친 것이 아니다.

## NOT_RUN·한계

직접 CUA/실브라우저, 픽셀·overflow·색 대비·실제 키보드 탐색·문서 전체 이동, Docker clean install/build, 전체 Geo pytest, 실제 PostgreSQL fence/취소·native retry daemon 및 Dagster 1.9는 수행하지 않았다. 부모 UI231/lint/type/build/backend/live 진척은 본인 결과로 산입하지 않았으며 진행 중인 live/CI를 완료로 판정하지 않았다. jsdom은 CSS 배치와 브라우저 inert의 실효를 증명하지 않는다. 서버 SSR 공격은 실제 Next 서버를 띄운 검증이 아니며 인증 성공 분기만 모의했다.

## 최종 판정

**BLOCK**. 기존 UI 두 finding은 수정 및 독립 회귀로 폐쇄되었다. UI·관측 경계 자체 검증은 통과했으나 고정 Python92eb의 C-CHILD-P1-01이 실제 등록된 복구 경로에 남는다. 이 결함 수정·pin 갱신과 최종 live/CI gate 확인 전에는 전체 소비자 후보를 승인할 수 없다.
