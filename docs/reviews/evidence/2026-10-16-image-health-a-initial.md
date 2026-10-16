# Geo577→578→579 독립 FULL 제품 검토 A — 최초 고정 후보

- 기준 main add5db1, Geo577 8a8fb95, Geo578 9a3d68770e0c4978b57228fb101785873d180486, Geo579 a316c340bd9ecec3d0eb0907f74dc830cbd8c0d2.
- 범위 FULL: 577 전체6파일·578 전체9파일·579 전체10파일과 관련 Dockerfile/Definitions/recovery/health route/Common 계약.
- 독립 판정: 577 SOURCE_PASS / P0·P1·P2 0. 578 CHANGES_REQUIRED / P2 1. 579의 신규 실행코드 P0·P1·P2 0이나 stack 전체는 아래 상속 문서 P2 미해결로 CHANGES_REQUIRED.
- 작성자 577 C/578·579 D, 다른 리뷰어 C/D raw·모형 미열람. 원본 Git object/선택 ext4 archive만 사용. 제품 source/기존 venv 수정·DB/SSH/운영/Docker/build0.

## GEO-A-P2-01: native recovery 활성화 필수 배포 전제 누락

docs/common-grpc-health-adoption.md:82–93은 private PID namespace/PID1 anchor/NTP/origin/Default launcher를 활성화 전에 확인한다고 기술하지만, 동일 exact origin의 singleton/exclusive 소유·rolling/blue-green/LB overlap 금지·구 init/startticks 및 실제 worker/cgroup 물리 소멸을 요구하거나 그 필수 공용 절로 연결하지 않는다.

최종 Common344의 docs/runbooks/dagster-adoption.md §15는 이 조건을 소비자 필수 활성화 전제로 명시한다. private PID namespace와 origin이 일치해도 구 서버와 worker가 살아 있는 overlap에서는 새 서버 sensor가 정상 구worker의 STARTED를 실패로 정산할 수 있다. 공용 센서가 구 namespace/routing을 직접 증명하지 않는다는 API 한계다. 이 조건은 과거 Common34 활성화 문서 finding으로 이미 정정된 경계다. syntactically valid env를 넣어도 기본 STOPPED이므로 현재 자동 활성화나 실제 피해가 발생했다는 주장은 아니다.

최소 수정은 Geo 활성화 안내에 singleton/exclusive, no overlap, 구 init·worker PID/startticks와 cgroup empty/gone 증명 및 UNKNOWN이면 STOPPED 유지, exact Common §15 링크를 추가하는 것이다. 제품 센서·스케줄·timeout·전역 설정 변경은 필요 없다.

## 코드·패키지 확인

577은 Dagster 패키지 Common pin/선택 grpc-health만 연결하고 core/API에 gRPC·Dagster를 새로 강제하지 않는다. 기존73e3의 __init__/dagster/deadline byte 보존 설명은 당시 pinad988/d1aa 비교다. 579는 API extra에 Common core-only를 추가하지만 core 기본 의존성은 그대로다.

578의 env guard는 None/blank이면 미등록, 정확 소문자40hex만 수용하며 잘못된 값은 원문 값을 로그에 쓰지 않고 skip한다. Default STOPPED·interval60 factory와 exact project/location/origin으로 연결한다. 기존 backup_verify만 retry1/나머지 jobs·resources·원 schedules/status·multiprocess1·기존 timeout/tags를 보존한다. Common 센서의 failure 정산과 기존 retry sensor의 요청 발행은 다른 책임이다. Defs import만으로 NTP/DB/failure mutation을 실행하지 않는다.

579 API/CS는 Common344 정확 VCS pin을 공유하고 CS extras/기존17 constraints 및 동일 builder/runtime f77 base·GDAL 병렬1·원 appuser/entrypoint를 유지한다. 실제 신규 의존성 compile/install 범위가 API extra에 한정된다. API Dockerfile의 git 추가는 VCS dependency 설치에 필요하다. final runtime/root 단계에서만 명시 stdlib compile1회, 이후 stdlib COPY가 없고 CS는 appuser로 돌아간다. 기존 Env·API exec CMD·user 권한과 회복 기본 STOPPED는 유지한다. bare API base floating tag는 원본에서 유지된 값이며 새 변경으로 introduced한 pin 회귀는 아니다.

이미지 API HC는 loopback /v1/healthz와 PORT fallback을 사용한다. 실제 router는 /v1 prefix의 DB 없는 상수 path다. timeout4는 Common 내부 논리예산이며 Python 시작 포함 Docker5초 보장이 아니다. interval10/timeout5/retries12/start30를 유지하며 header-only2xx·redirect 실패는 기존 urllib fullbody/redirect와 다른 계약임을 명시한다. Compose override 우선/Manager 별도 적용을 이미지 기본값 채택으로 오인하지 않는다. API/core DTO·인증·provider/DB·UI·기존 준비 경로는 byte 변경0이다.

## 직접 실행·반증

- immutable ext4 archive에 신규/변경3test 파일을 놓고 부모 conftest를 차단해 Python3.12/SDK1.13.24/실제Common344 venv를 읽기 전용 재사용했다. 신규 및 관련35 PASS/8warnings/2.67s. local 합성 TCP/gRPC health 이외 운영 endpoint/DB/SDK remote는 없다.
- 자체21조건: actual native factory AST만 inert sentinel로 실행해 missing/invalid origin 거절/정확 valid args, Dockerfile compile once, 실제 shell argv/default·empty·override PORT 및 성공/실패 exit 보존, API/core/CS extra 경계를 확인했다.
- 자체 초기 model은 PROJECT 상수 제공 누락으로 NameError였다. 원 stderr를 보존하고 모델 scope만 보강했다. 제품 실패/성공으로 세지 않는다.
- 원 테스트가 판별하는지 compile RUN 한 줄을 제거한 별도 mutant에서 실제 1FAIL/1PASS를 확인했다. 원 archive/원본 source는 변경하지 않았다.
- 두 기존 local source용 wheel을 직접 ZIP/전체 RECORD hash-size/METADATA 검사했다. Geo core167py·Dagster15py가 exact source와 동일, RECORD173/19개, Common344 API extra-only·CSdagster/grpc-health pin을 확인했다. 새 설치/빌드는0이며 이 wheel을 merged deployment artifact라고 부르지 않는다.
- full parent→head diff check PASS. source194 등 운영 image source 수는 이 wheel py182와 다른 범위이므로 합산하지 않는다.

author Python1915/Dagster148·전체 frontend·CI/운영 성과는 본인의 실행 수로 합산하지 않는다. 577 standalone의 과거 ad988 actual설치를 이번에 재실행한 것은 아니며 최종 후보 설치의 동일 grpc 경계35tests로 보강했다.

root의 현재 Geo-only UI8·latency14 실제 PASS는 baseline 증거다. 과거 dashboard ready503 FAIL과 분리하며 이번 source579의 actual deploy/성능 PASS로 승격하지 않는다. 운영 이미지 빌드/merged wheel/native pyc magic-hash·읽기 권한·효과/CPU/RSS는 후속 NOT_RUN이다. 모든 소유 도구 terminal.
