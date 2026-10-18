# Geo589·590·591 운영 배포 기록

## 완료와 대기 구분

2026-10-18 source d3dedb478bfcac026e3c51a44336109fd1662ee0의 공식 API·CS ARM64
빌드와 두 이미지 교체가 완료됐다. root 배포 attempt
4df684f4-a7da-43d9-9b98-cb18c2deb2d6는 두 대상 READY, 최종 PASS다.
공용 daemon OFF, 기존 QUEUED 집합 전후 동일, Geo native current run/physical worker 0을
배포 경계에서 확인했다. 문서 작성자는 root 실행을 자신의 실행으로 합산하지 않는다.

| 단계 | 현재 근거 |
| --- | --- |
| #589·#590·#591 source 머지 | 완료, 아래 source 표와 기존 독립 리뷰 기록 |
| 공식 API→CS 순차 빌드·격리 이미지 검사 | 작성자 직접 실행, 둘 다 PASS |
| Geo CS→API 이미지 교체 | root 직접 실행 PASS, 원본 컨테이너 보존·정상 종료 |
| 공식 활성 지문 STORE | root 단일 실행 PASS, 저장227.521초·daemon OFF·수명 불변 |
| n150 같은8표 지문과 비교 | MATCH, 8표 모두 같고 token 동일·DB/API 재조회 PASS |
| 배포 후 Admin 예제 UI | 초기 WebGL2 불가 FAIL 보존, n150 렌더링 환경 정정 후 동일 canvas 기준 두 모드 PASS |\n| 대시보드/Map 기준선 UI | 별도 대기, Admin 예제와 전체 UI 수용을 혼동하지 않음 |
| 새 CPU/RSS·실작업 SQL 취소·전체 Track1/2 | 이 기록에서 미실행/미완료 |

[공개 증거 요약](evidence/2026-10-18-geo-deployment.safe.json)은 image ID·설치 버전·원천 SHA·
배포 attempt를 결박한다. 비밀 환경 값·DB 연결 문자열·운영 원문 payload는 포함하지 않는다.

## 배포한 source

| 기능 | 검토 source / 머지 |
| --- | --- |
| #589 지문 파생 표 제외 | a6a9fcdf09656c29828113ada12cf2990d1d5d31 / 047536dc4346c341af78410a0407b4e1ba25af49 |
| #591 유지보수 죽은 연결 검사 | 제품78ea19760e1ecc47df1033e1f80e732791e4e0cc / d06b59b42e35ba5b0bced82974cd479bc941161c |
| #590 잠금 획득 예산·원 timeout 복원 | 제품fa3a779faa980cba621749f1a67c6ea8ddff7178, 통합bb6ef5ce675c9b4752d1943ffd2c88be94fed0fa / 최종d3dedb478bfcac026e3c51a44336109fd1662ee0 |

소스 리뷰·CI 근거는 기존 [#589](../reviews/2026-10-18-fingerprint-final.md),
[#590](../reviews/2026-10-18-radius-lock-closure/README.md),
[#591](../reviews/2026-10-18-worker-connection-closure/README.md)와 구분해 보존한다.
이번 문서 PR은 제품/스키마/잠금 값/CI workflow를 변경하지 않는다.

## 공식 이미지와 격리 검사

| 역할 | image ID | 설치 버전 |
| --- | --- | --- |
| API | sha256:e5ca22c96f40889d2463663e5f8123d07e473f6b1bff5b2342c77dacdbef703c | Python3.12.15 / SQLAlchemy2.1.5 / Dagster SDK 없음 |
| CS | sha256:3b21fc5e8fcd90ebb3f583cb413349f995665b3f6fd5681efcf913ef353dc3a5 | Python3.12.14 / Dagster1.13.24 / dagster-postgres0.29.24 / SQLAlchemy2.1.1 |

API는 공식 Dockerfile의 고정되지 않은 SQLAlchemy 의존성을 해석한 실제2.1.5다.
CS의 잠금2.1.1과 다르며 둘 다2.1.1이라고 주장하지 않는다. 기존 Dockerfile에는
GIT_COMMIT ARG가 없어 임의 인자를 넣지 않았다. OCI revision과 실제 설치 원문 hash로 확인했다.

API core168파일, CS core168+Dagster16파일이 source와 일치했다.
두 이미지 Common 원천은344d91c0eec4b605e007e61ce248693a729d692d다.
지문8표에서 region_radius_parts가 제외됐고 API 연결 검사 기본0,
CS 유지보수 연결 검사 source10000ms를 확인했다. GDAL3.10.3/Fiona1.10.1 actual import와
stdlib O0 checked-hash pyc 샘플5개씩을 검사했다.
격리 컨테이너는 network none/read-only, DB·provider·worker 실행0이며 종료 후 제거했다.

## 빌드 시간과 초기 실패 보존

모든 빌드 source/tmp/cache/log와 DockerRoot는 NVMe였다.
API 총2207.28초(36분47초), CS 총2445.65초(40분46초)였다.
API GDAL wheel525.71초·Fiona1163.6초, CS GDAL525.3초·Fiona1101.5초다.
초기 “GDAL 컴파일” 표현에는 Fiona가 포함됐으며 가장 긴 구간은 Fiona였다.
실제 CPU tick·로그 전진을 확인한 정상 컴파일을 중단하거나 재시작하지 않았다.
COPY src 이후 dependency compile 구조의 캐시 개선은 후속 후보이며 이번 변경0이다.
이는 실제 수집 CPU/RSS 절감 수치가 아니다.

첫 prepare74fe2beb-7d60-4d3d-9a54-0e9e586df453는 CS service label을
컨테이너 이름과 혼동해 PREFLIGHT에서 실패했다. 실제 key는 geo-dagster-code-server다.
SDK exec/Compose CAS/stop/create/start 전 차단됐고 원 UNKNOWN 기록을 보존했다.
controller r2는 해당 literal 한 곳만 수정했으며 selector/Compose9조건·기존 안전 경계9조건이 통과했다.
root가 새 UUID prepare를 성공시킨 후 별도 실제 배포했다. 실패 attempt를 재전송하지 않았다.

## 보존한 정책과 남은 수용

root 배포는 두 Geo image만 변경하고 기존 HC·limits·env·D4=21600·튜닝을 보존했다.
원본 대상은 정상 stop(-1)·PID/cgroup 소멸 후 보관했고 새 PID/ticks·healthy를 확인했다.
API/CS 새 CID와 큐 보존은 공개 증거에 있다. daemon을 시작하거나 센서를 활성화하지 않았다.

#589 정의변경에 따른 활성 지문은 root가 공식 ktgctl serving fingerprint-active STORE
한 번으로 저장했다(227.521초). 중복 전량 스캔을 위한 선행 dry-run은 하지 않았다.
n150의 같은8표 READONLY 결과와 표별 hash8개·token 모두 MATCH다.
새 token은 dd1-2f2ec5207609a2c1de57cbb64bebcb8f이며 DB와 API의 재조회도 PASS,
활성 릴리스1개·수명 불변을 확인했다. 원천 변경 없이 활성 메타데이터를 저장한 범위다.

root n150 Chromium1228 Admin 예제 attempt66efaadf는 처음 FAIL이었다. geometry=false
API200/OK·후보1·point 있음·728ms 뒤 canvas 대기 TimeoutError였고 geometry=true는 미실행이었다.
원 console/fallback 진단과 screenshot은 실패 전에 수집되지 않았으므로 첫 기록만으로 제품 오류로
단정하지 않았다. 별도 진단1회는 로그인 전 navigation Error로 끝났으며 API·지도 회귀와 분리했다.

추가 관측735478cb에서는 runtime key present=true/HTTP200, 두 주소 응답 모두 정상인데
blank page와 실제 page의 WebGL2=false, canvas0 및 “WebGL2를 지원하지 않습니다” fallback을
확인했다. 현재 CoordinateMap의 GPUInitializationError 안내와 일치하며 키 누락/주소 API 실패나
낡은 selector 때문이라는 근거는 없었다. 설치1223/1228 둘 다 Chrome149.0.7827.55였고
필요 GPU 공유 라이브러리는 존재했다.

n150 blank probe로 원 소프트웨어 렌더링3옵션에 --ignore-gpu-blocklist와
--disable-gpu-sandbox를 더하면 실제 WebGL2가 지원됨을 확인했다. 이는 소유 시험 브라우저의
설정이며 앱/컨테이너/서비스나 배포된 제품 보안 설정을 바꾸지 않았다.
Windows fallback은 사용하지 않았다. 기존 canvas visible assertion과 API 판정은 유지했고,
진단상 첫 실패 뒤 두번째 API도 관측할 수 있게 하되 overall FAIL 조건은 그대로 뒀다.

최종 attempt49fc068a는 n150 Linux에서 원 예제·include_geometry=false/true 둘 다 PASS다.
API 각각200/OK·후보1·point 있음, true는 building geometry를 반환했다.
두 모드 모두 canvas1·visible, WebGL2=true·키 존재·지도 오류/로딩/키/타일 fallback 범주0,
pageerror0·의도 밖 write0이었다. private screenshot2개는 공개하지 않는다.
183/415ms 응답 시간은 Transport Admin 빌드가 겹칠 수 있는 구간의 관찰이며 성능 개선으로
해석하지 않는다. 이 예제2모드는 전체 Admin/대시보드·T-325/Map 수용을 대신하지 않는다.

기존 G-01 a2의 실제 오래 걸리는 worker/SQL 취소 수용, 관리 UI 전체 T-325 및
reverse 성능·메모리·소비자 기준선은 이 배포 PASS만으로 닫지 않는다.
사용자 요청에 따라 문서 commit은 [skip ci]이며 문서 검증을 이유로 CI/전체 suite/이미지 재빌드를 추가하지 않았다. 위 UI는 별도 승인된 운영 수용 실행이다.
