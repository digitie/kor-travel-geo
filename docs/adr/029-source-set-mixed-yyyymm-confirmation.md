# ADR-029: 원천 자료 기준월은 source set으로 명시하고 혼합 적재는 확인 절차를 거친다

- 상태: accepted (T-045 구현 완료)
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

## 컨텍스트

도로명주소 한글 정본, 위치정보요약DB, 내비게이션용DB, 전자지도 SHP, 도로명주소 출입구 정보, 상세주소/구역 추가 레이어는 업데이트 주기가 다를 수 있다. 실제 로컬 검증에서도 도로명주소 한글 정본은 `202603`, 위치정보요약DB/내비게이션용DB/SHP는 `202604`, direct 출입구 자료는 `202605`처럼 서로 다른 기준월을 갖고 있었다.

기존 CLI 예시는 `ktgctl load all-sidos ... --yyyymm 202604`처럼 단일 기준월을 모든 child에 적용하는 형태였다. 이 방식은 실제 원천 월을 덮어써 감사 추적을 흐리게 만들 수 있고, 운영자가 의도적으로 최신 보조 자료를 섞은 것인지 실수로 다른 월의 자료를 고른 것인지 구분하기 어렵다.

또한 `/admin/load` UI는 대용량 자료를 다룬다. 업로드가 끝나기 전에 적재를 시작하면 실패 복구가 어렵고, 사용자는 업로드 진행률과 실제 적재 진행률을 구분해서 볼 수 없다.

## 결정

원천 묶음은 단일 `yyyymm`이 아니라 `source_set` 계획 객체로 표현한다. `source_set`은 원천별 기준월, 경로, checksum, 기준월 불일치 여부, 사용자 확인 여부를 함께 가진다.

1. 기준월 필드는 원천별로 분리한다. 예: `juso_yyyymm`, `parcel_link_yyyymm`, `locsum_yyyymm`, `navi_yyyymm`, `shp_yyyymm`, `roadaddr_entrance_yyyymm`, `sppn_makarea_yyyymm`.
2. CLI는 source set의 기준월이 서로 다르면 기본적으로 멈춘다. 대화형 실행에서는 원천별 기준월 표를 보여 주고, 사용자가 지정 문구를 입력해야 계속한다.
3. 비대화형 CLI, cron, CI는 prompt를 띄우지 않는다. 혼합 기준월을 허용하려면 `--allow-mixed-yyyymm`와 명시 confirmation token 또는 문구를 함께 줘야 한다.
4. API와 라이브러리는 사용자에게 묻지 않는다. 대신 디렉터리를 읽어 후보를 매칭하는 함수와, 각 원천 기준월/경로를 명시해 적재 계획을 만드는 함수를 분리한다.
5. UI는 다중 파일 선택과 drag and drop 업로드를 지원한다. 모든 파일이 서버에 저장되고 source set 분석이 끝난 뒤에만 적재를 시작할 수 있다.
6. UI에서 source set 기준월이 맞지 않으면 팝업으로 원천별 기준월을 보여 주고, 사용자가 의도한 혼합 적재인지 확인해야 한다.
7. 업로드 진행률과 적재 진행률은 별도 퍼센트로 표시한다. 업로드는 개별 파일/전체 upload set 단위로 취소 가능해야 하고, 적재는 root `full_load_batch` job cancel로 취소해야 한다.

## API/함수 경계

라이브러리와 REST 표면은 다음 세 단계를 분리한다.

1. 발견: `discover_load_sources(root_path | upload_set_id)`는 디렉터리 또는 업로드 묶음을 읽고 `SourceSetDiscovery`를 반환한다. 이 단계는 적재하지 않는다.
2. 계획: `build_full_load_source_set_plan(...)`은 원천별 기준월 또는 명시 경로를 받아 `SourceSetPlan`을 만든다. 기준월이 섞였는데 확인 정보가 없으면 실패한다.
3. 등록: `submit_full_load_source_set(plan)` 또는 기존 `POST /v1/admin/loads kind=full_load_batch`가 확정된 plan의 child payload를 큐에 등록한다.

REST는 `/v1/admin/load-sources/discover`, `/v1/admin/load-sources/plan`, `/v1/admin/uploads/*`, `/v1/admin/loads`로 나눈다. `/v1/admin/loads`는 prompt나 파일 발견을 수행하지 않고 확정된 payload만 받는다.

## 근거

- 실제 배포 주기 차이를 데이터 모델이 숨기지 않고 드러낸다.
- C10 정합성 결과가 "실수로 섞임"과 "운영자가 승인한 혼합 적재"를 구분할 수 있다.
- CLI는 운영자가 터미널에서 바로 판단할 수 있고, API/라이브러리는 자동화에 맞게 구조화된 warning과 plan을 반환한다.
- 대용량 업로드와 적재를 분리하면 네트워크 실패, 파일 누락, 기준월 mismatch를 DB 적재 시작 전에 발견할 수 있다.

## 결과 기준

- `load_jobs.payload.source_set`, `load_jobs.source_set`, `load_manifest.source_set`, `load_consistency_reports.source_set`에는 원천별 기준월과 확인 여부가 남아야 한다.
- `mixed_yyyymm=True`이면서 `mixed_yyyymm_acknowledged=False`인 batch는 등록 또는 C10에서 차단되어야 한다.
- UI의 `/admin/load` 상태 머신은 `idle → uploading → source_review → plan_ready → processing → finished`와 `cancelled`/`failed` 전이를 표현할 수 있어야 한다. 혼합 기준월 확인은 `source_review` 단계의 modal로 처리한다.
- 업로드 파일은 저장 완료 전에는 운영 원천으로 취급하지 않는다. partial file은 `*.part`로 저장하고, checksum 확인 후 atomic rename한다.

## 후속

- (done) T-045에서 DTO, CLI, REST, UI를 구현했다.
- (open) C10 정합성 SQL/리포트가 acknowledged mixed source set을 `INFO` 또는 `WARN`으로 표현하도록 보강한다.
- (open) 기존 `load all-sidos --yyyymm`는 새 `load full-set` 명시 기준월 모드로 대체하거나 deprecated 안내를 추가한다.
