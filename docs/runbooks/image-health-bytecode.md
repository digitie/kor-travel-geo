# Geo 이미지의 stdlib bytecode와 HTTP 생존 점검

## 변경과 범위

Common37의 고정 source344d91c0eec4b605e007e61ce248693a729d692d를
API extra에는 core-only로, Dagster 패키지에는 기존 dagster/grpc-health extra 그대로 설치한다.
core 라이브러리만 설치할 때 Common/Dagster/gRPC를 새로 강제하지 않는다.

두 Dockerfile은 Common 설치 후 **최종 이미지의 바로 그 Python interpreter**로
python -I -m kortravelcommon.build_bytecode --stdlib를 root 단계에서 실행한다.
worker1/optimize0/checked-hash를 사용하고 이후 stdlib를 덮어쓰지 않는다.
CS는 원 appuser로 돌아간다. PYTHONDONTWRITEBYTECODE·-I·원 GDAL/constraints·수집/복구/
스케줄·동시성·gRPC 상태 확인·native 센서 기본 STOPPED와 UI는 유지한다.
실패한 compile layer는 빌드 실패이며 entrypoint/health에서 자동 컴파일하지 않는다.
-I는 환경의 PYTHONDONTWRITEBYTECODE를 무시하지만, 유효한 pyc 읽기를 막지 않는다.
이 변경은 root 권한을 runtime 사용자에게 주거나 stdlib를 writable로 만드는 작업이 아니다.

API Dockerfile에 public /v1/healthz의 loopback HTTP 생존 확인을 기본값으로 선언한다.
PORT(기본12501)를 CMD와 같이 사용한다. interval은 사용자 지시로10s에서30s로 늘린다.
timeout5s/retries12/start-period30s와 Common 내부 전체 예산4초는 유지한다.
Geo API의 /v1/healthz는 DB 조회 없는 상수 상태 경로다. /v1/readyz의 DB/serving 준비와 별개다.
Common은 redirect/proxy/retry 없이 응답 헤더2xx만 검사한다.
기존 urllib의 redirect·응답 본문 전체 읽기와 의미가 동일하다고 주장하지 않는다.
느린/잘못된 본문을 이 새 생존 확인으로 보장하지 않으며 기존 API DTO/인증은 바꾸지 않는다.

**Compose의 명시 healthcheck는 이미지 HEALTHCHECK보다 우선한다.**
실제 Manager/운영 Compose에 기존 urllib override가 있으면 새 이미지 설치만으로 점검 명령이
바뀌지 않는다. 해당 소유 저장소의 명시 Test를 별도 리뷰·머지·배포로 연결해야 한다.
API 이미지에는 이전 Common 설치가 없으므로 새 core wheel/정확한 Geo 배포 metadata도
같이 설치한다. CLI 파일 한 개 복사나 기존 VCS metadata 유지로 채택 완료를 가장하지 않는다.

## 근거와 한계

격리된 실제 Geo CS 표본에서 import한 stdlib93개는 기본 cache가 없었고 site-packages54개는
유효했다. 같은 import의 self CPU가 약3.062초에서 별도 임시 cache warm0.940/0.928초로
줄었다. 이는 root의 동일 interpreter 표본이며 이 PR 최종 이미지/전체 서비스 CPU의 전후
개선 완료 증거가 아니다. 기본 HC의 self CPU3.04/3.02/3.37초 표본도 호스트 전체 CPU와
동일한 분모로 합산하지 않는다.

실제 API와 CS의 Python micro/minor가 같다고 추정하지 않는다. 각 최종 이미지 안에서
sysconfig stdlib·magic/cache tag·source hash·checked-hash flags3·읽기 권한을 확인한다.
다른 stage/Python 버전의 pyc 복사로 대체하지 않는다. 후속 layer에서 cache를 삭제하거나
source를 덮으면 효과가 사라진다. checked-hash 읽기에도 source 검증 비용은 남는다.

## 채택 순서와 수용 조건

1. Common37 및 선행 Geo577/578과 이 PR을 리뷰 후 머지한다. 고정 Common 커밋이
   Common main의 ancestor인지 확인하고 **머지된 Geo source**로 빌드한다.
2. 디스크가 적은 호스트에서는 기존 immutable API/CS 이미지 위에 정확한 새 Common 전체
   wheel와 Geo/GeoDagster wheel(metadata 포함)을 no-deps 설치하는 작은 layer를 준비할 수 있다.
   원 native/GDAL/의존성 버전을 임의 resolve·upgrade하지 않는다. core Common의 필수 추가
   전이 의존성은0이다. 기존 source·Config/Env/Cmd·HC·RootFS prefix와 새 의도 delta를 대조한다.
3. 해당 최종 interpreter/root에서 helper를 실행하고 읽기 전용 runtime 사용자에서도
   source/hash/magic에 맞는 stdlib pyc를 읽는지 검증한다. cache를 바꾸려는 동시 writer가
   없는 신뢰 빌드여야 한다. 실패를 자동 재시도로 숨기지 않는다.
4. Compose override 정산은 별도 승인 범위다. 원본 보존·정상 종료·source 확인 후 동일 workload/
   기존 HC argv와 새 API 후보 각각의 wall/self CPU·pyc 유효성·호스트 표본을 비교한다.
   cold prime/warm 반복·서버 CPU·관측기 부하를 구분한다.

Docker 이미지 빌드·운영 설치·서비스 재시작·실제 최종 pyc/ARM/성능 비교는 이번 소스 검증에서
NOT_RUN이다. unit loopback와 Dockerfile 명령 대역은 실제 이미지 실행의 대체 증거가 아니다.
DB/RustFS 생명주기·provider 호출·실제 튜닝 값은 이 PR 소유 범위가 아니다.


## 상태 점검 간격 3배 적용

2026-10-16 사용자 지시로 Geo API10→30초, code-server30→90초, UI10→30초로
점검 실행 간격만 늘린다. 데이터 수집·복구 센서·UI 데이터 조회 주기, 점검 명령과 실패 판정 횟수,
타임아웃·시작 유예는 기존 값을 유지한다. 실패가 발견되는 최대 지연도 길어지는 변경이다.

API 이미지 기본값 외 실제 Compose override에도 같은 간격을 반영해야 한다.
[간격 전용 override](../deploy/geo-healthcheck-cadence.yml)는 운영 정본의 서비스 이름 세 개에만
interval을 덮어쓰며 이미지·환경·원 Test를 포함하지 않는다. 기존 Compose 뒤에 병합하여
완성된 설정에서 실제 Test와 interval을 검증한다. 이미지 기본값만 바꾸거나 Compose 파일만
수정해 실행 중인 컨테이너에 적용됐다고 판단하지 않는다.

Geo를 계속 서비스하는 요구를 우선하여 전후에 Geo API/UI의 실제 응답과 다섯 컨테이너 상태를
확인하고, Weather와 Transport는 한 번에 한 스택씩 추가하여 별도 표본으로 기록한다.
점검 간격 변경과 stdlib cache·HTTP 점검 변경의 효과를 구분한다. 공유 DB/RustFS의 생명주기는
이 저장소에서 관리하지 않는다.
