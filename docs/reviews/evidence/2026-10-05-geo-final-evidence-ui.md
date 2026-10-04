<!-- SPDX-License-Identifier: GPL-3.0-only -->

# Geo 최종 common pin — 독립 리뷰 원본

- 실행 ID GEO-FINAL-A-20261005-4c59efe; 리뷰어 James (/root/review_ui).
- 관측 2026-10-04 23:02:17~23:05:49 UTC / 2026-10-05 08:02:17~08:05:49 KST.
- 저장소 F:/dev/kor-travel-geo-codex-dagster-common.
- base3f4ddc2dac3f31634a23ef0e9592f419e29e7d14.
- 실제 immutable candidate4c59efe3a778fb160b7d0a4fde2ca08967bf1531 (Git rev-parse 확인).
- Python pin73e3ff8b9398e533806d2d1a8435292570169de3. UI426/dev.3 SHA25603feae21b9e44041b648ba6d0defc3b16b97973ed3c7e70a83b91d279afb2f43 직접 확인.
- **최종 판정 PASS (독립 소스·실행 검증 범위)**. 신규 finding 없음. 외부 merge gate 완료와 구분한다.

## 격리·전체 delta

고정 Git show/diff/archive만 사용하고 /tmp/james-geo-final-4c59efe의 source archive에서 실행했다. source/install/mirror/dirty 원본/외부 서비스·DB를 변경하지 않고 기존 ext4 Node deps/Python venv를 읽기 재사용했다. 상대 원문·통합 판정/closure는 참조하지 않았다.

원 base 전체 UI·auth/menu·DTO·scope·snapshot·publication 계약은 앞선 본인 독립 검토와 연결했다. 596b→4c59 후속 제품 delta는 Python pin이며 ADR068의 고정SHA도 동일하게 갱신됐다. src와 UI가596b와 같은 객체 내용임을 고정 diff로 확인했다. 이후 문서 closure HEAD와 이 source 기준선을 혼동하지 않았다.

공통 full/light 판정은 작성자와 별도로 full 유지: 공개 UI/API/CSS·Python 복구/runbook 변경은 비면제다. reviewer 원본/disposition/index만의 closure 문서는 runtime 수정과 구분하며 재귀 full 재시작 예외가 가능하지만 새 규범/코드/gate 변경에는 적용하지 않는다. 소비자 역시 사용자 요청의 2인 독립 리뷰·live gate 대상이다.

## EXECUTED

- 고정 UI 소비자/자체 공격 **51 PASS**: named repository schedule URL, 미확인 job·tick, 모바일 collapsed 제목, 마지막 snapshot/선택상세 유지, unmount abort, login status/password/동시 제출, SSR encoded-tab 로컬 redirect, 쿠키 폐기·origin/rate·ref/aria 및 로그 keyboard region.
- 고정 postload_mv/batch_dag/infra_repo_sql **78 PASS,1.25초**.
- 이전 radius recorder 재현 PASS: 실제 refresh_mv의 MV commit 후 cancel_event set, 두 번째 publication guard에서 LoadJobLeaseLostError로 종료, guard2회·commit1회·radius_commit_after_cancel=false. 실제 PostgreSQL lock/rollback 실행이라고 주장하지 않는다.
- 새 pin 공통73e3의69건 및 본인 실제 SQLite 늦은 child/provider/metadata·legacy/native/budget 공격은 common-final-evidence-ui.md의 독립 실행으로 확인했다. 부모 테스트를 본인 실행으로 대신하지 않았다.

## 기존 본인 finding disposition

- G-UI-P2-01/P3-01: FIXED 유지, 동일 named-repository/mobile 조건 재검증 PASS.
- G-UI-P1-02 및 C-CHILD-P1-01: FIXED 유지, 느린 여러 페이지 진행.
- G-PUB-P1-01 및 C-PHASE-P1-01: FIXED 유지, 완료 뒤 새 provider 기록 요청0·태그0.
- G-PUB-P2-01: FIXED(source·독립 recorder), 두 MV 경로의 별도 serving radius commit도 guard로 확인. nativePG gate는 본인 NOT_RUN으로 구분한다.
- 공통 C-MERGE-P2-01: 새 pin에서 **FIXED**. 실제10초 outer deadline과3.1/5.1초 조회 지연을 유지한 본인 재현이 두 tick 요청1로 진행했다.
- 신규 소비자 P0/P1/P2/P3 finding 없음. 기존 원문 및 severity를 변경하지 않았다.

## 자체 재현·명령

/tmp/james-geo-final-4c59efe/radius_guard_probe.py
SHA25624d08e27b7a9a1a9f2016b151ac9423987b5a53fc621de3aa6ac2f5b65201108.
자체 통합/SSR 공격은 이전 immutable 후보의12+9건을 같은 조건으로 재사용했다.

```bash
cd /tmp/james-geo-final-4c59efe
PYTHONPATH=/tmp/james-geo-final-4c59efe/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python radius_guard_probe.py
PYTHONPATH=/tmp/james-geo-final-4c59efe/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_GEOIP_GATE_MODE=off /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python -m pytest -q tests/unit/test_postload_mv.py tests/unit/test_batch_dag.py tests/unit/test_infra_repo_sql.py --confcutdir=/tmp/james-geo-final-4c59efe/tests/unit

cd kor-travel-geo-ui
node /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/kor-travel-geo-ui/node_modules/vitest/vitest.mjs run --config /tmp/james-geo-final-4c59efe/james.vitest.config.mjs --configLoader native tests/unit/james.integration-attack.test.tsx tests/unit/james.ssr-attack.test.tsx tests/unit/dagster-panel.test.tsx tests/unit/app-shell-drawer.test.tsx tests/unit/auth.test.ts tests/unit/session-revocation.test.ts tests/unit/proxy-gate.test.ts tests/unit/backup-workflow.test.ts
```

## NOT_RUN·최종 판정

직접 browser/live/픽셀·실제 keyboard scroll, production/Docker build·전체suite·CI·실제 PG owner lock/MV rollback/release transaction/native daemon은 실행하지 않았다. 부모 PG/브라우저/live evidence를 본인 직접 실행에 산입하지 않고 진행 중인 외부 gate를 완료로 표시하지 않았다. jsdom/recorder는 의미·호출/commit 경계의 검증이며 실제 레이아웃·PG 정합성은 별도 gate다.

**PASS**: 본인 모든 code finding은 수정 확인됐고 신규 finding이 없다. 실제PG/live/CI·두 독립 원본의 full gate는 merge 담당이 별도로 확인해야 한다.
