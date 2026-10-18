# Geo591 독립 FULL 원문 — exact78ea

판정: **CONDITIONAL (제품 SOURCE_PASS, 문서 P3 후속)**.
OPEN P0=0, P1=0, P2=0, P3=1. 원 DSN argv P2는 FIXED.

검토자: James/A. 고정 시각 UTC: 2026-10-18T06:06:18.303845+00:00. 최초 시작 시각은 별도 보존하지 않아 미확인.
Manifest: /home/digitie/dev/geo590-591-p2-review-manifest-c-20261018.json
관찰 SHA256: db59678bc29832ee46e48c274d6191591536abeeadcfb2c562bfafe65d67e3b7
공통 base: 535e26b936978704a3c1ea12b1c15e840321ccdf.

이 검토는 제품 전체 delta와 연결 소스/문서/테스트를 읽은 독립 검토다. 다른 리뷰어의 새 원문/모형을 읽지 않았다. Git show/archive로 exact object를 사용했으며 제품/인덱스/branch를 수정하지 않았다. 현재 root가 원본 WT에서 후속 수정 중인 사실은 관찰했으나 이 보고서 판정에는 포함하지 않는다. 읽은 AGENTS/SKILL/README/agent-workflow/failure-patterns/ADR068 규칙을 적용했다. D4=21600·maintenance 6h·Daemon OFF는 변경되지 않는다.

실제 요청 원문(대화에 보존된 전달 메시지):
> 513freeze받았고B/C 독립리뷰배정했습니다. 이제Geo590/591독립fullreview 진행해주세요. C가590deadline입구체크/591testDSNargv제거 P2수정곧push, 최신freeze먼저C에게확인하여 fixedsnapshot을검토해주세요. WT /home/digitie/dev/kor-travel-geo-codex-lock-takeover-20261018 및 lifecycle-takeover-20261018. base535e26b. reviewerB원문은독립판정전읽지말고 자체source 전체(잠금상한/죽은worker쿼리cleanup)검토, source수정0/운영0. Managerhandoff 경로도보고부탁.
>
> 최종Geo59064ed012f15e20693d1eafa28b4cc70a536041bc7 /59178ea19760e1ecc47df1033e1f80e732791e4e0cc push됨. 해당head로검토해주세요. CHANGELOG P3도최종원문에고정해주시면root단순docsfix후delta확인요청하겠습니다. C현재Managerreview전환.

검증 격리: WSL Ubuntu-26.04, 자기 소유 Git archive 및 임시 fixture. 원 저장소 conftest/env 로딩을 제외하고 plugin autoload를 껐다. 순수 원본 unit 실행에는 네트워크/socket connect·주소 resolve·subprocess·실제 Dagster import를 차단했다. Pytest interpreter /home/digitie/dev/kor-travel-geo-codex-test/.venv/bin/python (Python3.13.14/SQLAlchemy2.0.50)을 읽기 전용으로 사용했다. 추가590 실제함수 AST 반례 로그의 interpreter는 Python3.12.13이다. CodeGraph 대상 CLI 실행은 미확인/NOT_RUN이며 target 전체 graph coverage를 주장하지 않는다.

실제 PostgreSQL, backend/worker signal, Dagster SDK, Docker, SSH, provider, 실데이터/키, 운영, daemon 실행은 NOT_RUN. CI는 제공된 별도 증거이며 본인 실행으로 세지 않았다. source PASS와 운영 수용을 분리한다. SQL timeout/server kernel 동작의 운영값을 추정하지 않는다. 새 CI/full suite/실서비스 조작은 하지 않았다.

## 고정 범위와 검사
Head78ea19760e1ecc47df1033e1f80e732791e4e0cc. base→head14파일353+/11-. manifest 파일목록 exact 일치, immutable diff --check exit0.
settings/infra engine/maintenance resource 연결, 신규 실제PG integration 및 child 계약, Dagster 구조 테스트와 CI/docs 전체 delta를 읽었다.
소유 archive /home/digitie/dev/geo591-snapshot-a-6lioftc1.
원본 test_dead_client_child_contract.py + test_infra_engine_pnu_sql.py **11PASS /0.80s**.
로그 /home/digitie/dev/geo591-unit-source-a-20261018.public.log.

## 이전 DSN argv P2 disposition — FIXED
eded91d 원본에 최종 child 계약2테스트만 올린 자기 archive에서 **2FAIL/0.64s**, final78ea 원본11unit PASS.
RED archive /home/digitie/dev/geo591-old-red-a-gb3zkgfb; 로그 /home/digitie/dev/geo591-old-child-argv-red-a-20261018.public.log.
현재 child argv는 app UUID/interval만 전달하고 DSN은 상속 env에서 읽는다. 원문 DSN이 출력되지 않는 unit assertion도 실행했다. fake subprocess만 사용했고 실제 child/DB/signal은0이다.

## 계약/회귀 검사
- src/kortravelgeo/settings.py:49 default0/ge0. API/default engine에는 별도 GUC를 추가하지 않는다.
- src/kortravelgeo/infra/engine.py:28–31은 positive 설정에만 connection option을 더하며 statement_timeout/search_path를 보존한다.
- kor-travel-geo-dagster/src/kortravelgeo_dagster/resources.py:201–243은 immutable model_copy로 maintenance engine만 statement_timeout0/client checker10000ms를 적용한다. AsyncAddressClient의 원 설정 및 원 engine disposal 흐름은 유지한다.
- 실제 Settings/_connect_options와 exact AST maintenance clone을 사용하는 자기 script own_settings_contract_a.py를 실행해 default/positive/negative/API격리/원Settings불변/기타필드동일을 확인했다(**script PASS**). 로그의 “12 assertions”는 수동 label이며 독립 테스트12개로 합산하지 않는다.
- 실제PG integration은 disposable guard/unique application_name/owned child만 대상으로500ms dead-client와0 control을 비교하도록 구성됐다. CI no-skip floor도 확인했다. reviewer는 이 integration을 실행하지 않았다.
- 문서는 Linux socket close 감지와 dead process에 범위를 제한하며 살아 있으나 멈춘 worker, FIN없는 네트워크 단절, raw/sync COPY/SHP/SPPN/pg_dump child까지 보장한다고 쓰지 않는다. 새 server global 변경/취소 API가 아니다.
- 기본0은 이 코드가 override하지 않는다는 의미다. DB 자체 GUC가0이라는 운영 사실로 단정하지 않는다. maintenance의 명시10000ms override는 문서화된 정책이다.
- source rebuild test의 ephemeral instance 정리는 테스트 수명 변경이며 제품 스케줄/daemon 동작 변경이 아니다.

## G591-A-P3-01 — CHANGELOG 누락
위치 CHANGELOG.md(변경 부재), public Settings :49 및 maintenance resource :201 연결.
새 KTG_PG_CLIENT_CONNECTION_CHECK_INTERVAL_MS/maintenance10s 범위를 요구된 additive changelog에 기록하지 않았다. root가 수용한 후속 docs 수정은 별도 closure 대상으로 이 exacthead에서 OPEN이다.

## 한계/최종
지원값과 소스 연결의 독립 source 검토는 PASS이며 새 P0/P1/P2를 찾지 못했다. 실제 서버의 dead-client kernel/PG 동작, Docker/worker 종료 후 PG query 정리, 운영 성능/CPU/메모리/장애복구 수용은 이 보고서 PASS에 포함되지 않는다. 제공 CI/작성자 실측과 자기 실행을 혼합하지 않았다.
