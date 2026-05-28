# DECISIONS — Architecture Decision Records

본 문서는 `kraddr-geo` / `kraddr-geo-ui` 프로젝트의 의사결정을 시간순으로 누적한다. 결정이 뒤집힐 때도 이전 기록은 지우지 않고 `superseded by ADR-XXX`로 표시한다.

## ADR 표준 형식

```
# ADR-NNN: <결정 요약>

- 상태: proposed | accepted | superseded by ADR-XXX
- 날짜: YYYY-MM-DD
- 결정자: <agent | human>

## 컨텍스트
<무엇이 문제였나. 어떤 제약·요구가 있었나.>

## 결정
<무엇을 정했는가. 한 문장으로.>

## 근거
- 

## 결과(긍정)
- 

## 결과(부정)
- 

## 후속
- (open) 추가 검증 필요한 사항
```

---

## ADR-001: PostgreSQL + PostGIS를 1차 저장소로 채택한다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
이전(v1) 구현은 SQLite + SpatiaLite를 사용했다. 확장 로드 가능 여부가 실행 환경마다 달랐고, 대량 적재(전국 11개 마스터 + 도형) 시 쿼리 성능과 동시성 제어가 부족했다. EXPLAIN 결과의 재현성도 떨어졌다.

### 결정
PostgreSQL 16 + PostGIS 3.4를 1차 저장소로 채택한다. SpatiaLite 기반 구현은 `v1` 브랜치에 보존하고 `main`에서는 더 이상 유지보수하지 않는다.

### 근거
- 도로명주소 전자지도(SHP) 적재에 GDAL Python binding이 안정적으로 동작
- `pg_trgm`, `unaccent`, MV(머티리얼라이즈드 뷰), 윈도우 함수 등 쿼리 도구 풍부
- `psycopg` async 드라이버로 SQLAlchemy 2 async 패턴과 자연스럽게 결합
- 디버거 EXPLAIN과 운영 쿼리가 같은 환경에서 평가됨

### 결과(긍정)
- 쿼리 튜닝의 자유도(인덱스 hint, `SET LOCAL`, 파티셔닝 등)
- 운영 표준 도구(pg_dump, repmgr 등) 활용 가능

### 결과(부정)
- 배포 의존성 증가(PostgreSQL 서버 운영)
- 단일 파일 배포(SpatiaLite의 장점)가 사라짐

### 후속
- (open) ARM 8GB 환경에서 `pg_pool_size`, `statement_timeout`, `work_mem`의 권장값 실측

---

## ADR-002: 라이브러리 API는 async-only로 둔다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
이전 구현은 동기/비동기 메서드를 둘 다 제공했다(`get_coord` + `aget_coord`). 코드 경로가 두 배가 되어 유지보수 비용이 컸다.

### 결정
`AsyncAddressClient`만 둔다. 동기가 필요한 사용자는 `asyncio.run`으로 감싼다.

### 근거
- 동기 인터페이스는 `asyncio.run` 한 줄로 충분히 대체
- FastAPI, SQLAlchemy 2, httpx 모두 async 중심
- 단위 테스트도 `pytest-asyncio`로 일원화

### 결과(긍정)
- 코드 경로 단순화, mypy strict 통과 용이
- 배치 처리(`geocode_many`) 시 동시성 제어가 자연스러움

### 결과(부정)
- 동기 컨텍스트(Jupyter, 단순 스크립트)에서 한 줄 래퍼 필요

---

## ADR-003: 응답 구조는 vworld와 호환되도록 유지한다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
`kraddr-geo`이 vworld의 드롭인 대체로 쓰일 수 있어야 한다는 요구가 있다. 동시에 자체 부가 정보(`bd_mgt_sn`, `zip_source`, 신뢰도 등)도 노출해야 한다.

### 결정
응답 최상위 키(`service`, `status`, `input`, `refined`, `result`)는 vworld 그대로 따른다. 자체 확장은 `x_extension` 키 하나에 모은다.

### 근거
- 기존 vworld 소비자 코드 수정 없이 도입 가능
- 확장 필드는 명확히 분리되어 호환성을 깨지 않음

### 결과(긍정)
- 폴백(`fallback="api"`) 시 vworld 원응답과 자연스럽게 섞임
- OpenAPI 스키마가 단정적

### 결과(부정)
- `x_extension` 외 필드 추가는 즉시 거절해야 한다 — 리뷰어 규율 필요

---

## ADR-004: ORM 위에 raw SQL Repository를 둔다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
지오코딩 쿼리는 CTE와 윈도우 함수를 다용하고 EXPLAIN 결과를 손튜닝해야 한다. ORM의 표현력은 부족하고 디버깅이 어렵다.

### 결정
`infra/*_repo.py`는 `sqlalchemy.text()`로 raw SQL을 직접 실행한다. ORM 모델(`infra/models.py`)은 read-only 매핑 용도로만 둔다.

### 근거
- `text()`는 EXPLAIN 결과를 그대로 재현하기 쉬움
- 인덱스 hint, `SET LOCAL`을 자유롭게 사용 가능
- 안전성: pydantic DTO가 결과를 검증하므로 타입 누수 없음

### 결과(긍정)
- 쿼리 튜닝이 백엔드 PR 안에서 일관됨
- 새 인덱스 추가 시 ORM 매핑 갱신 불필요

### 결과(부정)
- 컬럼 변경 시 SQL을 손으로 갱신해야 함 → CI에서 컬럼 존재성 통합 테스트로 방어

### 후속
- (open) bulk INSERT에 SQLAlchemy Core를 쓸지 검토

---

## ADR-005: 로더는 `ogr2ogr` subprocess 대신 GDAL Python binding을 쓴다

- 상태: **partially superseded by ADR-012** (텍스트 정본 1차로 전환, GDAL은 polygon/폴리라인 적재에만 사용)
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
이전 구현은 `ogr2ogr` subprocess를 사용했다. stderr 파싱, 진행률 미보고, 환경변수 누수 등 비용이 컸다.

### 결정
`osgeo.gdal.VectorTranslate`를 in-process로 호출한다. CP949 디코딩은 `open_options=["ENCODING=CP949"]`로 명시. `PG_USE_COPY`는 `gdal.config_options` 컨텍스트 매니저로 한정 적용(`gdal.SetConfigOption` 전역 호출 금지).

### 근거
- 진행률 callback으로 0~1.0 보고 — 작업 큐와 UI 프로그래스바 연결
- callback 안의 `cancel_event` 확인으로 협조적 취소
- subprocess 의존, stderr 파싱 비용 제거

### 결과(긍정)
- 작업 상태 관찰이 깔끔. 취소 동작 신뢰성 ↑
- 환경변수 누수 위험 사라짐

### 결과(부정)
- GDAL Python binding 의존성 추가(설치 환경 까다로움) — Docker 이미지로 표준화

---

## ADR-006: 적재 작업은 단일 백엔드 인스턴스의 in-process 큐로 직렬 처리한다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
관리 UI가 적재를 트리거할 때 HTTP 요청이 길어지고 진행률을 폴링할 방법이 필요하다. 동시에 여러 시도를 병렬 적재하면 ARM 8GB 환경에서 `work_mem`/IOPS가 한꺼번에 고갈된다.

### 결정
`api/_jobs.py`에 `asyncio.Queue` + `Semaphore(1)` 기반 in-process 큐를 둔다. 단일 백엔드 인스턴스 가정. 다중 인스턴스가 필요해지면 Redis(RQ) 또는 PostgreSQL `LISTEN`/`NOTIFY`로 같은 인터페이스 유지하며 확장한다.

### 근거
- 동시 실행 1개 → 자원 고갈 방지
- 진행률·취소·log_tail이 단일 프로세스 메모리에 자연스럽게 살아 있음
- 외부 큐 시스템 도입 비용 회피

### 결과(긍정)
- 운영 단순. 작업 상태가 즉시 보임
- 사용자가 화면을 닫아도 적재는 끝까지 진행

### 결과(부정)
- 프로세스 재시작 시 진행 중 작업 손실 → 매니페스트 기반 재개 필요
- 다중 인스턴스 배포 불가(향후 ADR로 재검토)

---

## ADR-013: 프론트엔드 UI는 내부망 전용, 애플리케이션 인증 없음

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
`kraddr-geo-ui`는 운영자·개발자용 디버깅/관리 도구다. 사용자 대상 서비스가 아니다.

### 결정
이 UI는 외부 인터넷에 노출하지 않고 사내망/VPN 뒤에서만 접근 가능하도록 배포한다. NextAuth, 미들웨어 가드, `X-Admin-Key` 헤더, 세션 쿠키 등 애플리케이션 레벨 인증을 두지 않는다. 보안 경계는 네트워크 레벨(nginx IP allowlist 또는 사내 SSO 게이트웨이)에서 만든다.

### 근거
- 디버거 워크플로(주소 입력 → 지도 클릭 → EXPLAIN)에 인증 마찰이 비용 대비 효과 없음
- 네트워크 단 보호가 더 강력하고 운영 변경만으로 충분

### 결과(긍정)
- UI 코드와 백엔드 코드에 인증 로직이 침투하지 않음
- `Next.js → 백엔드`는 동일 origin/VPC라 CORS·인증 헤더 불필요

### 결과(부정)
- 외부 노출이 필요해지면 운영(nginx/SSO 게이트웨이) 변경이 선행되어야 함
- 마지막 수단으로 NextAuth 도입 시 새 ADR로 명시

### 후속
- (open) 운영 환경별 네트워크 정책 문서 정리

---

## ADR-014: 기본 예외명은 `KraddrGeoError`로 둔다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex

### 컨텍스트
초기 사양에는 base 예외명이 `AddrKrError`로 적혀 있었다. 그러나 현재 패키지 식별자는 `kraddr.geo`로 확정되었고, 아직 공개 릴리스 전이라 외부 catch 코드와의 호환성 부담이 낮다.

### 결정
base 예외명은 `KraddrGeoError`로 둔다. 장기 호환 alias는 만들지 않는다.

### 근거
- 패키지명과 public API 이름이 일관된다.
- 공개 릴리스 전 변경이므로 임시 alias 없이 정정하는 편이 단순하다.
- downstream이 catch할 안정 base class 이름을 초기에 확정한다.

### 결과(긍정)
- 예외 계층이 `kraddr.geo` 식별자와 맞는다.
- `AddrKrError`/`KraddrGeoError` 혼용을 피한다.

### 결과(부정)
- 이전 사양 초안을 기준으로 코드를 작성한 사용자가 있다면 import를 수정해야 한다.

---

## ADR-015: `kraddr`는 implicit namespace package로 둔다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex

### 컨텍스트
이 저장소는 `kraddr.geo` 서브패키지를 제공한다. 향후 같은 환경에 `kraddr.tour` 같은 다른 `kraddr.*` 패키지가 설치될 수 있다. `src/kraddr/__init__.py`를 두면 PEP 420 namespace 병합을 막아 충돌 가능성이 생긴다.

### 결정
`src/kraddr/__init__.py`를 두지 않고 `kraddr`를 PEP 420 implicit namespace package로 둔다.

### 근거
- 여러 배포 패키지가 `kraddr.*` 하위 이름을 공유할 수 있다.
- parent package 소유권을 이 저장소가 독점하지 않는다.
- setuptools는 namespace package discovery(`namespaces = true`)로 `kraddr.geo`를 패키징한다.

### 결과(긍정)
- 향후 `kraddr.*` 패키지와 같은 Python 환경에서 공존하기 쉽다.
- parent namespace에 불필요한 public API가 생기지 않는다.

### 결과(부정)
- 도구 설정에서 namespace package를 명시적으로 고려해야 한다.

---

## ADR-008: 로더 의존성은 시스템 GDAL과 동일 버전으로 핀한다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

### 컨텍스트
ADR-005에서 `osgeo.gdal.VectorTranslate`를 in-process로 호출하기로 했다. Python `gdal` 패키지는 C++ 확장이라 시스템 `libgdal-dev`의 헤더·라이브러리에 빌드 시 의존하며, 런타임 ABI도 일치해야 한다. `pip install gdal>=3.8`만으로는 wheel이 시스템과 다른 버전을 가져와 `ImportError: undefined symbol` 또는 segfault가 발생할 수 있다.

### 결정
`loaders` extra는 시스템 GDAL과 **정확히 같은 버전**의 Python 바인딩에 핀한다. WSL 개발 환경에서는 다음 절차를 따른다.

```bash
sudo apt install -y libgdal-dev gdal-bin
pip install "gdal==$(gdal-config --version)"
pip install -e ".[loaders]"
```

운영·CI는 `osgeo/gdal:ubuntu-small-*` 베이스 Docker 이미지를 사용해 시스템 GDAL과 Python 바인딩 버전을 한 번에 묶는다(ADR-005 후속). conda 사용자는 `conda-forge`의 `gdal`을 쓰면 같은 효과.

### 근거
- Python `gdal`은 순수 파이썬이 아니라 C++ 확장 wheel. 시스템 GDAL과 ABI가 일치해야 안전.
- `gdal-config`가 PATH에 있어야 wheel 빌드가 성공하므로 `libgdal-dev` 설치가 사실상 의무.
- Docker 베이스를 표준화하면 운영·CI에서 환경 일관성을 보장.

### 결과(긍정)
- 적재 단계의 reproducibility 확보 — 같은 시스템 GDAL 위에서 같은 바인딩이 보장됨.
- T-013(`SidoLoader`)에서 “설치는 됐는데 import 시 죽는” 케이스 제거.

### 결과(부정)
- 사용자가 `pip install -e ".[loaders]"`를 바로 실행하면 실패할 수 있어 `docs/dev-environment.md` 안내가 필수.
- 다중 환경(ubuntu LTS·conda·Docker) 모두 문서화 부담.

### 후속
- (open) Docker 이미지(`docker/Dockerfile.loaders` 등) 작성은 T-013과 함께.
- (open) GDAL upstream의 PEP 517 build backend 전환이 있으면 `gdal-config` 의존을 줄일 수 있음 — 재검토.

---

## ADR-009: 우편번호는 epost OpenAPI(15000302) ZIP을 분기 1회 전량 적재해 로컬 매칭한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

### 컨텍스트
우편번호 매칭은 본 프로젝트의 핵심 lookup 흐름 중 하나(`docs/data-model.md`의 4단계 우선순위, `docs/reverse-geocoding.md`의 `zip_at` 분기). 외부에서 활용할 수 있는 OpenAPI는 크게 두 종류다.

- 데이터셋 **`15000302`**: 우정사업본부 우편번호 **다운로드** 서비스. 호출 응답은 ZIP 파일 URL(`fileLocplc`)로, 매칭 결과를 직접 주지 않는다. `downloadKnd ∈ {1=전체, 2=변경분, 3=범위주소, 4=사서함주소}`.
- 데이터셋 **`15056971`**: 우정사업본부 우편번호 **정보조회** 서비스. 키워드/주소로 우편번호를 실시간 lookup.

또한 `15000302`의 `downloadKnd=2`(변경분)를 누적 적용해 점진 갱신할지, `downloadKnd=1`(전체)을 정기적으로 받아 전량 교체할지의 선택지가 있다.

### 결정
우편번호 매칭은 **데이터셋 `15000302`의 `downloadKnd=1`(전체) ZIP을 분기당 1회 받아 로컬 PostgreSQL(`postal_pobox`, `postal_bulk_delivery`)에 TRUNCATE 후 INSERT 하는 방식**으로 운영한다. `downloadKnd=2`(변경분) 누적은 운영하지 않는다. 데이터셋 `15056971`(실시간 lookup)은 본 시점에서 **도입하지 않는다**.

### 근거
- 우편번호 데이터셋은 분기 단위로도 충분히 안정적 — 일/주 단위로 변경분을 추적할 운영 부담이 비용 대비 이득 없음.
- 전량 TRUNCATE→INSERT는 변경분 머지(`MVM_RES_CD` 흐름과 별개)보다 적재 로직이 단순하고 idempotent. T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 비용 절감.
- 매칭은 로컬 DB가 1차이고 외부 API 호출은 폴백/보조(`fallback="api"`, ADR-003 후속). 실시간 lookup API(`15056971`)를 도입하면 라우터에 외부 호출 경로가 또 늘어나며, 응답 형식이 vworld 호환 응답(`x_extension`)과 결합되지 않아 어댑터 비용이 추가된다.
- ADR-005, ADR-006의 적재 운영 모델(GDAL 적재 + 직렬 작업 큐)과 같은 패턴으로 cron 또는 관리 UI(T-015) 트리거 한 줄에 통합 가능.

### 결과(긍정)
- 적재 코드가 단순. `postal_*` 테이블은 분기당 일관성이 보장.
- 외부 API 의존도가 분기당 4회(전체 1 + 보조 3종 중 필요 시) 정도라 쿼터에 여유.
- vworld 호환 응답 구조가 외부 lookup API로 오염되지 않음(ADR-003 유지).

### 결과(부정)
- 분기 내 신규 우편번호(예: 신축 건물의 새 우편번호)는 다음 갱신까지 누락 가능. 운영상 큰 영향은 없지만, 사용자 신고가 들어오면 수동 변경분 적재(`downloadKnd=2`)로 임시 보강하는 절차가 필요할 수 있다.
- 실시간 외부 lookup이 필요한 신규 use-case가 생기면 본 ADR을 뒤집어야 함 — 그때 새 ADR로 재검토.

### 후속
- (open) 적재 cron 스케줄(분기 첫째 주 일요일 02:00 KST 등)을 운영 단계에서 확정. `kraddr-geo load pobox/bulk` CLI를 systemd timer로 묶는 안이 자연스러움(T-018).
- (open) 사용자 신고 기반 hot-fix(특정 우편번호만 변경분 적재) UI는 `/admin/postal`(T-023)에 가벼운 보조 액션으로 추가 가능.

---

## ADR-010: PNU 토지구분 매핑은 infra 레이어에서 조립한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

### 컨텍스트
법원 등기·토지대장 등 외부 기관 시스템과 조인하려면 19자리 표준 PNU(필지번호)가 필요하다. PNU 11번째 자리(토지구분)는 표준상 `1=일반, 2=산`이지만, 도로명주소 원천(`tl_spbd_buld.mntn_yn`)은 `0=대지, 1=산` 체계라 직접 결합하면 외부 조인 시 조용히 틀린다.

### 결정
- PNU 11번째 자리 매핑: **`mntn_yn='0' → '1'`, `mntn_yn='1' → '2'`**. helper 또는 generated stored column 어느 쪽이든 본 매핑을 그대로 따른다.
- 조립 위치: **`infra/`** (또는 generated column). `core/`는 의미론적 `mntn_yn`만 보관하고 PNU라는 외부 식별자 표준은 저장/조회 계층의 책임으로 분리.
- helper 함수 시그니처: `pnu_from_row(row: dict) -> str` (19자리). 컬럼명 표준은 `docs/data-model.md` "PNU 조립" 절.

### 근거
- 외부 시스템 조인 use-case가 사양에 진입했으므로 PNU 매핑을 별도 ADR로 박아두면 향후 hardcode 사고를 방지할 수 있다.
- `core/normalize.py`는 입력 문자열을 의미론적으로 해체하는 책임이지 외부 식별자 표준에 맞춰 재조립하는 책임이 아니다 — 계층 책임 분리(ADR-004).
- generated stored column이면 SQL one-liner로 자동 유지되어 적재 변경분이 와도 자연 갱신.

### 결과(긍정)
- 외부 시스템 조인 데이터의 무결성이 매핑 hardcode에 의존하지 않음.
- 라이브러리 사용자가 `bd_mgt_sn`이 아닌 PNU로 외부 조인할 때 안전한 단일 경로 제공.

### 결과(부정)
- generated column 추가 시 마이그레이션 비용(기존 행 백필). 첫 풀로드 단계라 부담은 낮다.
- helper 방식이면 라우터/리포가 호출을 잊을 가능성 — 따라서 generated column 권장.

### 후속
- (open) T-006(DDL) 또는 T-016(reverse/zipcode 코어) 진행 시 generated column 채택 여부 최종 결정. 기본 권장은 generated stored column.
- (open) 외부 시스템(등기·토지대장) 응답 구조와 PNU 자릿수 조합 실데이터 검증.

---

## ADR-011: 적재 작업 큐 상태는 `load_jobs` 테이블로 영속화한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

### 컨텍스트
ADR-006은 적재 작업을 `asyncio.Semaphore(1)` 기반 in-process 큐로 직렬 처리하기로 했다. 그러나 분기 풀로드 한 사이클이 30~60분에 달하는 경우 다음 위험이 누적된다.

1. **프로세스 재시작 시 상태 손실**: uvicorn reload, 컨테이너 재기동, 배포 전환으로 `JobQueue._jobs` dict가 휘발. `state=running`이던 작업이 폴링 API에서만 사라지고 DB에는 부분 적재 상태로 남는다.
2. **다중 워커**: `uvicorn --workers N` (N>1) 운영 시 in-process Semaphore가 워커마다 갈라져 동시 실행 위험.
3. **재기동 후 큐잉 잔여**: `state=queued` 작업의 payload 파일(`uploads/*.zip`)이 사라졌는데 큐만 살아 있으면 실행 시 즉시 fail.

ADR-006 결과(부정)의 "매니페스트 기반 재개 필요" open 항목을 본 ADR로 구체화한다.

### 결정
- `load_manifest`는 "성공한 적재의 watermark"로 유지하고, 작업 실행 상태는 **별도 `load_jobs` 테이블**로 분리한다 (`job_id`, `kind`, `payload JSONB`, `state`, `progress`, `current_stage`, `source_checksum`, `error_message`, `started_at`, `finished_at`, `heartbeat_at`, `created_at`).
- `JobQueue`의 상태 전이(`queued → running → done|failed|cancelled`)는 매번 `load_jobs` UPDATE를 동반한다. 진행률/current_stage는 1~5초 throttle로 갱신.
- **lifespan startup 복구**:
  - `state='running'` → 무조건 `failed`로 마크 (재시작으로 끊긴 작업).
  - `state='queued'` → payload(`uploads/*.zip`) 파일이 있으면 재큐잉, 없으면 `failed`.
- **다중 워커 안전성**: 워커가 작업 픽업 직전 `pg_try_advisory_lock(ADVISORY_SLOT_LOAD_QUEUE)` + `FOR UPDATE SKIP LOCKED`로 DB 수준 직렬성 보강. 단일 워커 환경에서도 비용 무시 수준이라 항상 적용.

### 근거
- ADR-006의 in-process 큐는 단일 인스턴스를 가정했지만, 분기 풀로드 60분 동안 reload가 발생할 확률을 0으로 둘 수 없다.
- `load_manifest`(watermark)와 `load_jobs`(실행 큐)를 분리해야 "마지막 성공 적재가 언제인지"와 "지금 실행 중인 작업이 뭔지"의 두 질문이 서로 오염되지 않는다.
- advisory lock + SKIP LOCKED는 PostgreSQL이 제공하는 표준 패턴 — 외부 큐 시스템(Redis/RQ) 도입 없이도 다중 워커 안전성 확보.

### 결과(긍정)
- uvicorn reload/컨테이너 재기동 후에도 작업 상태가 정확히 복구됨.
- `/v1/admin/jobs`가 in-memory 휘발 없이 항상 DB 진실을 반영.
- 다중 워커 운영이 가능해져 ADR-006의 단일 인스턴스 가정을 점진적으로 풀 수 있음.

### 결과(부정)
- `load_jobs` 테이블 추가 마이그레이션(T-006). 진행률 throttle 로직 추가 복잡도.
- payload 영속화로 `uploads/`의 정리 정책(30일 cron)이 `load_jobs.state='done'` 이후로 명확히 묶여야 함.

### 후속
- (open) T-006 DDL에 `load_jobs` 포함. T-015 `_jobs.py` 구현 시 본 ADR의 lifespan recovery + advisory lock 패턴 사용.
- (open) `uvicorn --workers N` 운영 결정은 별도 ADR — 본 ADR은 N>1 가능성을 열어두기만 한다.

---

## ADR-007: `mv_geocode_target`은 건물당 대표 출입구 1건만 보유한다

- 상태: accepted (위치정보요약DB 기반으로 갱신, ADR-012 후속)
- 날짜: 2026-05-23
- 결정자: human

### 컨텍스트
출입구 데이터(`tl_locsum_entrc`, 위치정보요약DB 기반)는 한 건물(`BD_MGT_SN`)에 출입구가 여러 개일 수 있다. 평면화 MV가 단순 join으로 다대다를 펼치면 `UNIQUE (bd_mgt_sn)` 인덱스가 깨지고 `REFRESH MATERIALIZED VIEW CONCURRENTLY`가 불가능하며, 도로명/지번 lookup 결과도 출입구 수만큼 부풀어 라우터가 추가 dedup 로직을 떠안는다.

### 결정
`mv_geocode_target`은 건물당 **대표 출입구 한 건**만 보유한다. 선택 순서(SQL `DISTINCT ON (bd_mgt_sn)` 기반):

1. `ent_se_cd = '0'` (대표 출입구 코드) 우선
2. `buld_se_cd`(지상/지하)와 일치하는 출입구
3. 모호하면 `ent_man_no` 오름차순 첫 한 건

비대표 출입구가 필요한 use-case(내비 진입점, 차량 진입 등)는 `tl_locsum_entrc` 또는 `tl_navi_entrc`를 직접 조회한다. 출입구가 0개인 건물은 ADR-012 후속으로 `tl_navi_buld_centroid`의 centroid를 fallback 좌표로 사용한다.

### 근거
- 지오코딩 라우터가 `bd_mgt_sn` 단위 단일 row를 가정하므로 `UNIQUE` 인덱스 + CONCURRENTLY refresh 사용 가능.
- 위치정보요약DB의 `ent_se_cd`는 SHP보다 명확해 대표 선택 규칙이 안정적.
- 역지오코딩은 처음부터 `tl_locsum_entrc` 전체에서 GiST 최근접을 찾기 때문에 MV 단순화의 부담이 없다.

### 결과(긍정)
- 도로명/지번 lookup 결과가 항상 0 또는 1건. 라우터 로직 단순.
- ADR-011 (load_jobs)과 결합해 적재→swap→이전 MV drop 흐름이 깔끔.

### 결과(부정)
- 비대표 출입구·내비 진입점 응답이 필요해지면 별도 조회 경로 필요(ADR-012가 텍스트 보조 테이블로 흡수).

### 후속
- (open) `ent_se_cd` 값 분포가 시도별로 다른지 실데이터 검증 — ADR-012의 정합성 검증 리포트에 포함.

---

## ADR-012: 적재는 행안부 텍스트 정본 1차 + SHP polygon 보조 하이브리드로 한다

- 상태: accepted (ADR-005를 부분 supersede)
- 날짜: 2026-05-23
- 결정자: human

### 컨텍스트
첨부 사양서는 도로명주소 전자지도(SHP) 11개 마스터를 1차 데이터로 가정했다. 그러나 행안부는 같은 정보를 텍스트 정본 3종으로도 제공하며, **텍스트가 raw 정본**이고 SHP은 도형 적재용으로 가공된 파생물이다.

| 자료 | 정본성 | 무엇이 들어있는가 |
|------|--------|-------------------|
| 도로명주소 한글_전체분 (월간) | 도로명주소·지번·우편번호·법정동·행정동의 **정본** | 좌표 없음. BD_MGT_SN ↔ 행정 매핑이 가장 완전 |
| 위치정보요약DB_전체분 (월간) | 출입구 좌표(EPSG:5179)의 **정본** | BD_MGT_SN + ent_man_no, ent_se_cd 명확 |
| 내비게이션용DB_전체분 (월간) | 내비 진입점·차량 진입점·건물 centroid의 **정본** | 출입구가 없는 건물의 fallback 좌표 |
| 도로명주소 전자지도 SHP (월간) | **polygon/폴리라인의 정본** | 행정구역·우편번호·건물·도로 도형 |

SHP만으로는 행정동 코드(`adm_cd`, vworld 응답 `level4A`/`level4AC`)와 출입구 분류가 충분하지 않다. ADR-005가 GDAL VectorTranslate로 모든 적재를 묶었던 결정은 사양 완성도 측면에서 손해다.

### 결정
**적재를 두 경로로 분리한다.**

| 경로 | 대상 | 도구 | 의존성 |
|------|------|------|--------|
| **텍스트 1차** (`loaders/text/`) | `tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc` | stdlib `csv` + `psycopg.copy()` | GDAL 불필요 |
| **텍스트 선택 보조** (`loaders/text/`) | `tl_roadaddr_entrc` | stdlib `csv` + `psycopg.copy()` | T-039 이후 direct 출입구 선택 적재 |
| **SHP 보조** (`loaders/shp/`) | `tl_scco_ctprvn/sig/emd/li`, `tl_kodis_bas`, `tl_spbd_buld_polygon`, `tl_sprd_manage/intrvl/rw` | GDAL Python binding (ADR-005 한정 유지) | `libgdal-dev` |

`tl_spbd_buld_polygon`은 BD_MGT_SN PK만 공유하고 **속성은 모두 `tl_juso_text`에서** 채운다 — 도형과 속성의 책임을 명확히 분리.

`mv_geocode_target`은 텍스트 1차 + 출입구 좌표 + centroid fallback을 합쳐 구성한다(`docs/data-model.md`). `pt_source ∈ {entrance, centroid}` 컬럼으로 응답에 좌표 출처를 노출한다. T-039 이후 direct 출입구와 위치정보요약DB 출입구는 모두 호환성상 `entrance`로 분류하고, 세부 원천은 운영 테이블과 정합성 sample에서 추적한다.

### 근거
- **정본 우선**: 행정동 코드, 도로명 텍스트, 우편번호 정본이 모두 텍스트에서 raw로. SHP DBF에 의존하지 않음.
- **GDAL 의존성 축소**: 텍스트 적재는 stdlib만으로 동작. GDAL 환경 셋업 실패가 전체 적재를 막지 않음(polygon만 GDAL 필요).
- **출입구 0개 건물 fallback**: 내비게이션용DB centroid가 빈자리를 메움 — 사양에 fallback 경로가 자연스럽게 박힘.
- **v1 코드 경험**: v1 `store.py`/`data.py`가 이 세 텍스트를 이미 다뤘음 — 컬럼 매핑·CP949 디코딩 노하우를 reference로.

### 결과(긍정)
- 응답 완성도 ↑ — 행정동 정보가 vworld 호환 응답 전체에 자연스럽게.
- 적재 환경 의존성 감소 — GDAL 없이도 80% 적재 가능. polygon만 GDAL.
- 출입구 없는 건물의 fallback이 사양 단계에서 해결.
- 텍스트와 SHP 사이의 BD_MGT_SN 정합성 검증으로 데이터 무결성 회귀 감지.

### 결과(부정)
- 마스터 테이블 종류 증가(11 → 14). MV 정의 복잡도 ↑(단 라우터는 MV만 보면 됨).
- 두 변동분(텍스트 월간 + SHP polygon 월간) 기준일 정합성 운영 책임 추가 — `load_manifest`에 `source_set` 표기로 해결.
- 라이선스 표시 의무(공공누리 1형) — 운영 README/응답 메타에 명시.

### 후속
- (open) ADR-005의 GDAL Python binding 결정은 polygon 적재에만 한정 — 본문 supersede 표시 완료.
- (open) 텍스트 변동분(`도로명주소 한글_변동분`, `위치정보요약DB_변동분`)의 누적 적용 정책은 ADR-009(우편번호) 모델 따라 분기 풀로드만 운영하는 옵션 검토.
- (open) 정합성 검증 리포트(`docs/data-model.md` "정합성 검증")의 임계값(예: 좌표 오차 95th percentile < 5m)을 실데이터로 캘리브레이션.

---

## ADR-016: 적재 진행 상태와 정합성 리포트는 라이브러리·API로 일급 노출한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

### 컨텍스트
ADR-006(in-process 큐)과 ADR-011(`load_jobs` 영속화)이 작업 상태를 DB에 적었지만, 외부 라이브러리 사용자(`AsyncAddressClient`)는 작업 큐 표면에 접근할 일이 직접 없다. 또한 ADR-012의 텍스트↔SHP 정합성 검증 결과를 디버그 UI(`kraddr-geo-ui /admin/load`)와 라이브러리 사용자가 모두 봐야 한다.

### 결정
다음을 사양에 일급 추가한다.

1. **`AsyncAddressClient.load_status(job_id)` / `load_jobs(limit, kind)`** — 적재 작업 상태/진행률/`current_stage`/`log_tail` 조회. 라이브러리 사용자가 자체 앱에서 직접 폴링 가능.
2. **`POST /v1/admin/loads`** + **`GET /v1/admin/loads/{job_id}`** + **`GET /v1/admin/loads?kind=...&state=...`** — REST 표면. WebSocket `/v1/admin/loads/{job_id}/stream`은 선택(structlog 라인 push).
3. **`AsyncAddressClient.consistency_report(report_id?)` / `run_consistency_check(scope)`** — 텍스트↔SHP 정합성 리포트 생성/조회. ADR-012의 검증 케이스(아래)별 결과를 구조화된 JSON으로 반환.
4. **`POST /v1/admin/consistency/run`** + **`GET /v1/admin/consistency/{report_id}`** + **`GET /v1/admin/consistency`** — REST.

### 근거
- 적재가 분기 풀로드로 30~60분 걸리므로 진행 상태가 외부에 노출되어야 운영 자동화가 가능.
- 정합성 리포트는 한 번 생성하고 보관(`load_consistency_reports` 테이블)해 시계열로 회귀 추적.
- 디버그 UI가 같은 라이브러리·REST 함수를 호출하므로 별도 어댑터 없이 일관.

### 결과(긍정)
- 외부 앱이 적재 cron을 자체 관찰 가능.
- 정합성 회귀(예: 텍스트와 SHP 좌표 95th percentile 오차가 갑자기 증가)가 자동 감지 가능.

### 결과(부정)
- 라이브러리 API 표면이 늘어 mypy/import-linter 부담 약간 증가.
- WebSocket 스트리밍은 T-015 작업 큐와 분리해서 추가하는 게 안전(별도 후속).

### 후속
- (open) `consistency_report`의 임계값과 알람 정책은 운영 단계에서 캘리브레이션.
- (open) WebSocket `/v1/admin/loads/{job_id}/stream`은 T-015 본체 구현 후 별도 PR.

---

## ADR-017: 전국 풀로드는 batch DAG와 정합성 게이트를 통과한 뒤 MV swap을 수행한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex, PR #10 review 반영

### 컨텍스트

ADR-011은 작업 상태를 `load_jobs`에 영속화하고 단일 작업을 직렬 실행하도록 했다. 그러나 분기 단위 전국 풀로드는 단일 파일 적재가 아니라 **여러 정본/보조 데이터셋이 한 묶음으로 성공해야만** 운영 조회면에 노출할 수 있는 작업이다.

예를 들어 `tl_juso_text`만 새 월분으로 갱신되고 `tl_spbd_buld_polygon`이 이전 월분으로 남은 상태에서 `mv_geocode_target`을 swap하면, API는 "새 텍스트 + 옛 도형"의 가짜 정합성 결과를 반환한다. 이 상태는 SQL 오류가 아니라 데이터 운영 오류라서 단순 `state='done'`만으로는 막을 수 없다.

### 결정

전국 풀로드는 `full_load_batch` root job 아래에 child job을 둔 **DAG**로 실행한다.

1. root job: `kind='full_load_batch'`, `load_batch_id = job_id`, 상태는 batch가 끝날 때까지 `running`.
2. 1단계 source load child 6종:
   - `juso_text_load`
   - `juso_parcel_link_load` (T-038에서 추가)
   - `locsum_load`
   - `navi_load`
   - `shp_polygons_load`
   - `pobox_load`
3. 1단계 child가 모두 `done`이면 큐가 자동으로 `consistency_check`를 등록한다.
4. `consistency_check`는 `load_consistency_reports.source_set.load_batch_id`에 batch id를 기록한다.
5. 정합성 리포트의 `severity_max`가 `ERROR`이면 batch root를 `failed`로 마크하고 `mv_refresh`를 등록하지 않는다.
6. 정합성 리포트가 `OK`/`INFO`/`WARN`이면 `mv_refresh` child를 `payload.strategy='swap'`으로 자동 등록한다.
7. `mv_refresh`가 끝나면 batch root를 `done`, `progress=1.0`으로 마감한다.

`load_jobs`에는 다음 두 컬럼을 추가한다.

```sql
load_batch_id TEXT,  -- 같은 batch에 속한 root/child를 묶는 id. root는 자기 job_id와 동일.
parent_job_id TEXT   -- root job_id. child가 어떤 batch root 아래인지 추적.
```

### 근거

- 풀로드에서 중요한 것은 개별 파일 적재 성공이 아니라 **동일 기준월 데이터셋 묶음의 원자적 노출**이다.
- 정합성 검증을 batch DAG의 게이트로 두면, 사람이 실수로 `mv_refresh --swap`을 먼저 실행하는 운영 사고를 줄일 수 있다.
- 별도 외부 workflow 엔진을 도입하지 않고도 `load_jobs`와 기존 직렬 큐만으로 재시작 이후 상태 추적이 가능하다.

### 결과(긍정)

- 부분 성공 데이터가 API 조회면에 노출되는 경로가 명확히 차단된다.
- `load_batch_id`로 운영 로그, 진행률, 정합성 리포트, MV swap 이벤트를 한 화면에서 묶어 볼 수 있다.
- `log_tail`/`current_stage`가 root와 child 모두에 남아 장애 분석이 쉬워진다.

### 결과(부정)

- 단순 FIFO 큐보다 상태 전이가 복잡하다. 특히 `consistency_check`가 리포트를 쓰지 않고 성공 처리되는 경우를 별도 실패로 막아야 한다.
- child 구성은 현재 기본 6종으로 고정되어 있다. 우편번호 대량배달처(`bulk_load`)까지 batch 필수 구성으로 넣을지는 운영 데이터셋 확보 후 조정한다.

### 구현 규칙

- source child 중 하나라도 `failed`/`cancelled`가 되면 batch root를 `failed`로 마크하고 아직 `queued`인 같은 batch child는 `cancelled` 처리한다.
- `consistency_check` 성공 후에도 `load_consistency_reports`에 `load_batch_id`가 붙은 최신 리포트가 없으면 `mv_refresh`를 등록하지 않는다.
- `mv_refresh`는 평시에는 concurrent refresh를 쓸 수 있으나, batch DAG가 자동 등록하는 풀로드 후속 작업은 `strategy='swap'`을 사용한다.

---

## ADR-018: PostGIS 보조 extension은 `x_extension` 스키마에 격리한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex, PR #10 review 반영

### 컨텍스트

PostGIS, `pg_trgm`, `unaccent`는 운영 DB에 반드시 필요한 extension이지만, 마스터 테이블과 같은 `public` 스키마에 섞어 두면 다음 문제가 생긴다.

1. DDL 리뷰에서 extension 객체와 서비스 테이블이 섞여 스키마 책임이 흐려진다.
2. 실수로 `DROP SCHEMA public CASCADE` 또는 테스트 초기화 스크립트가 extension 객체까지 건드릴 수 있다.
3. 권한 분리, 백업/복구, diff 리뷰에서 "서비스 데이터"와 "DB 기능 제공 객체"를 구분하기 어렵다.

### 결정

extension은 전용 스키마 `x_extension`에 설치한다.

```sql
CREATE SCHEMA IF NOT EXISTS x_extension;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA x_extension;
SET search_path = public, x_extension;
```

애플리케이션 연결은 `options=-csearch_path=public,x_extension`를 사용한다. Alembic, raw SQL repository, loader, CLI 모두 같은 search path를 전제로 한다.

### 근거

- `public`은 서비스 테이블·MV·인덱스의 기본 스키마로 유지하고, extension 제공 함수/타입은 별도 영역에 둔다.
- PostGIS 함수(`ST_DWithin`, `ST_Transform` 등)를 SQL에서 schema prefix 없이 쓸 수 있으면서도 객체 소유권은 분리된다.
- 리뷰어가 DDL을 볼 때 extension 설치 위치를 명확히 확인할 수 있다.

### 결과(긍정)

- extension과 서비스 DDL의 책임 경계가 선명하다.
- 테스트 DB 재생성·운영 DB 권한 점검 시 extension 영역을 별도로 확인할 수 있다.
- 누군가 `CREATE EXTENSION ... WITH SCHEMA public`으로 되돌리는 변경을 ADR 위반으로 리뷰할 수 있다.

### 결과(부정)

- 모든 연결 경로가 `search_path=public,x_extension`를 지켜야 한다. 누락되면 PostGIS 함수 탐색 오류가 날 수 있다.
- 운영 DB에 이미 `public` 스키마로 설치된 extension이 있다면 초기 마이그레이션 전에 정리 절차가 필요하다.

---

## ADR-019: 프론트엔드 런타임은 Next.js 16을 보안 하한선으로 둔다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex, PR #12 구현

### 컨텍스트

초기 문서는 `kraddr-geo-ui`를 Next.js 14 기반으로 설계했다. 그러나 PR #12에서 실제 패키지를 부트스트랩하며 `npm audit --omit=dev`를 실행한 결과, Next.js 14 계열에는 2026년 기준 production high advisory가 남아 있었다. 신규 UI를 처음 도입하는 시점에 이미 high 취약점이 보고된 major를 고정하면, 내부망 전용 도구라 해도 운영 배포 전 보안 검토에서 다시 major upgrade를 요구받을 가능성이 높다.

### 결정

`kraddr-geo-ui`는 Next.js 16을 보안 하한선으로 둔다. React는 Next.js 16.2.6의 peer 범위가 허용하는 React 18.3.1을 유지한다. Node.js는 Next.js 16의 engine 조건에 맞춰 20.9 이상을 사용한다.

### 근거

- Next.js 16.2.6은 npm registry 기준 React 18과 React 19를 모두 peer로 허용한다.
- 기존 App Router 구조, Route Handler 프록시, TanStack Query 기반 클라이언트 컴포넌트는 Next.js 16에서도 큰 구조 변경 없이 동작한다.
- `npm audit --omit=dev --audit-level=high`가 통과하도록 high 취약점은 제거한다. Next.js 내부 `postcss` moderate advisory는 upstream dependency 해결 전까지 PR 본문에 잔여 위험으로 남긴다.

### 결과

- 프론트엔드 문서의 프레임워크 표기는 Next.js 16으로 갱신한다.
- CI는 Node.js 20을 사용하고 `npm ci`, `npm run gen:types`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 실행한다.
- 향후 Next.js minor/patch 업데이트는 `npm audit --omit=dev --audit-level=high`를 기준으로 빠르게 흡수한다.

---

## ADR-020: 디버그 UI 지도는 VWorld WMTS + MapLibre를 사용하고 wrapper도 적극 보강한다

- 상태: accepted, amended by ADR-028 and ADR-032
- 날짜: 2026-05-25
- 결정자: 사용자 요청, codex 구현

### 컨텍스트

PR #12까지의 `kraddr-geo-ui`는 Kakao Maps SDK를 기준으로 좌표 지도 컴포넌트를 만들었다. 그러나 이 프로젝트의 백엔드 응답은 vworld 호환 구조를 1차 공개 표면으로 삼고 있고, 외부 폴백도 vworld 주소 좌표 API를 먼저 호출한다. 디버그 UI가 다른 지도 공급자 위에서만 동작하면 운영자가 실제 vworld 기반 응답과 지도 타일을 같은 조건으로 비교하기 어렵다.

별도 저장소 `digitie/maplibre-vworld-js`는 MapLibre GL JS 위에서 VWorld 지도 layer, marker, cluster를 재사용 가능한 형태로 제공하려는 목적에 맞다. PR #15 최초 리뷰 시점에는 GitHub 의존성으로 설치했을 때 package `exports`가 가리키는 `dist/` 산출물이 포함되지 않아 소비자 프로젝트에서 직접 import하면 build 실패 위험이 있었다. 이후 upstream PR #6/#7이 merge되어 `dist/`, `exports`, `types`, `style.css`, zod v4 peer dependency가 정리되었고, PR #9 이후 click/error/flyTo helper와 tile error helper까지 소비한다.

### 결정

`kraddr-geo-ui`의 디버그 지도는 Kakao Maps SDK가 아니라 VWorld WMTS + MapLibre GL JS를 사용한다.

- 브라우저 환경변수는 `NEXT_PUBLIC_VWORLD_API_KEY`다. 실제 키는 `.env.local`에만 두고 저장소에는 커밋하지 않는다.
- 지도 타일 URL, style 생성 규칙, CSS import는 `digitie/maplibre-vworld-js`의 package API를 사용한다. `kraddr-geo-ui/lib/vworld.ts`는 로컬 구현을 갖지 않고 `maplibre-vworld`의 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `isVWorldTileError()`, `redactVWorldUrl()`, `VWorldLayerType`를 재수출한다. 단, 내부 컴포넌트 import 안정성을 위해 `redactVWorldUrl as redactVWorldTileUrl` alias를 둔다.
- `maplibre-vworld` package는 CI에서 SSH key 없이 설치할 수 있도록 검증된 최신 `main` SHA 또는 최신 stable release로 고정한다. 현재 확인된 최신 SHA는 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`이다. upstream이 npm registry release 또는 stable tag를 제공하면 lockfile drift와 검증 결과를 확인한 뒤 dependency spec을 바꾼다.
- `maplibre-vworld/style.css`를 전역 CSS에서 import해 MapLibre GL 기본 CSS와 upstream package CSS를 한 경로에서 가져온다.
- `VWorldMap` 컴포넌트 전체 대체는 단계적으로 검토한다. 현재 `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`는 디버그 화면 전용 동작, 즉 지도 클릭 시 `(lon, lat)` callback, key 미설정 fallback, transient overlay 임계치, marker 즉시 이동, SSR 차단 wrapper를 직접 보장한다. VWorld tile 오류 분류와 URL redaction은 `maplibre-vworld`의 `isVWorldTileError()`/`redactVWorldUrl()` helper를 사용한다.
- `digitie/maplibre-vworld-js`에서 패키징, 타입, CSS import, Next.js 호환성, VWorld layer/marker/cluster 공통 문제가 발견되면 이 저장소 전용 workaround에 그치지 않고 upstream도 적극 수정한다. 단, geocode/reverse 디버그 입력, API 응답 overlay, 정합성/성능/적재 상태 표시처럼 `kraddr-geo-ui`에만 의미가 있는 특화 기능은 이 저장소의 domain wrapper에서 구현한다.

### 근거

- 디버그 UI가 백엔드의 vworld 호환 응답과 같은 공급자의 지도 타일 위에서 좌표를 확인할 수 있다.
- MapLibre는 표준 WebGL 지도 엔진이므로 VWorld WMTS 외에도 후속 SHP/GeoJSON overlay, consistency sample 표시, load 검증 layer를 붙이기 쉽다.
- `digitie/maplibre-vworld-js`를 개선하면 이 저장소뿐 아니라 다른 VWorld/MapLibre 소비자도 같은 보강을 재사용할 수 있다.

### 구현 규칙

- 좌표 callback과 marker 입력은 기존과 동일하게 `(lon, lat)` 순서를 유지한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없거나 tile loading이 실패하면 같은 크기의 fallback preview를 보여 주어 CI/내부망/키 미등록 환경에서도 화면이 깨지지 않게 한다.
- 실제 VWorld key는 문서, 코드, 테스트, PR 본문에 평문으로 남기지 않는다.
- `maplibre-vworld` package root import는 `npm ci`, type-check, Next.js build에서 계속 검증한다. 패키지 SHA를 바꿀 때는 `dist/`/`types`/`exports`/`style.css` 포함 여부를 먼저 확인한다.
- Next.js App Router에서 `maplibre-gl`은 브라우저 전역 객체와 WebGL에 의존하므로, 상위 디버그 화면은 `next/dynamic(..., { ssr: false })`로 지도 컴포넌트를 지연 로딩한다.
- VWorld tile fetch 실패는 일시적 네트워크/zoom 범위 문제일 수 있으므로 즉시 치명 overlay로 고정하지 않는다. transient tile error는 redacted URL로 경고만 남기고, 누적 임계치를 넘거나 style/WebGL 계열 오류일 때만 사용자에게 실패 상태를 표시한다.
- VWorld `Satellite`/`Hybrid` 계열은 z18까지만 요청하도록 레이어별 `maxZoom`을 둔다. `Base`/`gray`/`midnight`는 z19까지 허용한다.
- `maplibre-vworld`의 현재 style source id는 `vworld-${layerType}`이고, `Hybrid`는 `vworld-satellite`와 `vworld-Hybrid`를 함께 사용한다. tile error source 판별은 특정 id 하나가 아니라 `vworld` prefix를 기준으로 한다.
- 향후 CSP를 도입하면 VWorld tile 호출을 위해 `connect-src`/`img-src`에 `https://api.vworld.kr`를 포함해야 한다.

### 결과

- `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`가 지도 렌더링과 click/marker 동작을 담당한다.
- `kraddr-geo-ui/components/vworld/LazyCoordinateMap.tsx`가 Next.js dynamic import, SSR 차단, skeleton UI를 담당한다.
- `kraddr-geo-ui/lib/vworld.ts`는 upstream package의 VWorld helper 재수출 지점이다.
- `maplibre-vworld` GitHub 의존성은 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`로 갱신했다. React 18 소비자와 upstream zod v4 peer dependency를 맞추기 위해 `kraddr-geo-ui`도 `zod ^4.4.3`을 직접 의존성으로 둔다.
- 프론트엔드 문서와 외부 API 문서는 Kakao Maps가 아니라 VWorld WMTS 기준으로 갱신한다.
- 후속 PR에서는 `CoordinateMap`의 디버그 UI 전용 동작을 `maplibre-vworld-js`의 재사용 가능한 props/hook/test로 옮길 수 있는지 검토한다. 이때 바로 컴포넌트 전체를 교체하지 않고 click callback, marker 제어, tile error hook, fallback surface, SSR-safe 사용 방식을 항목별로 맞춘다.

---

## ADR-028: 디버그 UI 지도 구현은 `maplibre-vworld-js`를 최신으로 소비하고 domain wrapper로 경계화한다

- 상태: accepted, amended by ADR-032
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

> 최신 운영 정의는 ADR-032를 우선한다. ADR-028의 초기 표현인 "완전 포팅"은 `kraddr-geo-ui` 특화 기능까지 upstream으로 옮긴다는 의미가 아니라, 범용 VWorld/MapLibre primitive는 최신 `maplibre-vworld-js`에서 소비하고 이 저장소의 geocode/reverse/admin 특화 UX는 domain wrapper로 경계화한다는 의미로 개정됐다.

### 컨텍스트

ADR-020은 Kakao Maps SDK를 제거하고 VWorld WMTS + MapLibre GL JS를 디버그 UI 지도 표준으로 정했다. 이후 `kraddr-geo-ui`는 `digitie/maplibre-vworld-js`를 GitHub SHA로 소비하며 tile URL, style 생성, maxZoom, tile error 분류, URL redaction helper와 CSS를 upstream package에서 가져온다.

그러나 현재 `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`는 MapLibre map instance, marker, click callback, transient tile error overlay, fallback preview를 직접 wiring한다. 이 직접 wiring에는 두 성격이 섞여 있다. VWorld WMTS style, layer, marker primitive, package export 같은 범용 기능은 `maplibre-vworld-js`가 책임지는 것이 맞지만, `kraddr-geo-ui`의 geocode/reverse 디버그 입력, 오류 overlay UX, API 응답 좌표 표시 같은 이 저장소 특화 기능은 `maplibre-vworld-js`로 밀어 넣지 않는다.

### 결정

후속 T-044에서 디버그 UI 지도 구현은 `maplibre-vworld-js`의 최신 public API를 소비하되, `kraddr-geo-ui` 특화 기능은 이 저장소의 domain wrapper에 남긴다.

경계화의 의미는 다음과 같다.

1. `kraddr-geo-ui/components/vworld/CoordinateMap.tsx`는 직접 `new maplibregl.Map(...)`, source/layer 생성, marker lifecycle, tile error 분류를 소유하지 않는다.
2. VWorld style/layer, tile URL, maxZoom, marker primitive, 공통 tile error/redaction, package `exports`/`types`/`style.css` 계약은 `maplibre-vworld-js`의 public API에서 제공한다.
3. `kraddr-geo-ui`는 도메인별 wrapper를 유지한다. wrapper의 책임은 API 응답 좌표를 `(lon, lat)`로 넘기고, geocode/reverse 디버그 폼과 skeleton, 오류 overlay 문구, 내부 분석 상태를 연결하는 것이다.
4. `NEXT_PUBLIC_VWORLD_API_KEY` 미설정 fallback, SSR-safe 사용, transient tile error overlay, redacted logging, marker 즉시 이동, click callback `(lon, lat)` 순서가 기존 디버그 UI 동작과 동일해야 한다.
5. `maplibre-vworld-js`에 범용 기능·타입·패키징·테스트가 부족하면 upstream을 직접 수정한다. 반대로 `python-kraddr-geo`의 주소 디버깅, 작업 상태, 정합성/성능 분석, API 응답 표시처럼 이 라이브러리 특화 기능은 이 저장소에서 구현한다.
6. `maplibre-vworld-js`는 사용할 때마다 최신 `main` 또는 최신 stable release를 확인하고, 검증된 최신 버전으로 갱신한다. 임시로 오래된 SHA에 고정하는 것은 허용하지 않는다.

### 구현 절차

T-044는 두 저장소를 함께 다루는 작업으로 본다.

1. `python-kraddr-geo`에서 현재 `CoordinateMap` 계약을 목록화한다.
2. `maplibre-vworld-js` 최신 `main` 또는 stable release를 확인하고, dependency가 최신인지 비교한다.
3. 부족한 범용 upstream 기능은 `maplibre-vworld-js`에 먼저 구현한다.
   - VWorld layer/style helper
   - controlled/uncontrolled marker primitive
   - `flyToOptions`와 즉시 이동 옵션
   - VWorld tile error 분류와 URL redaction
   - SSR-safe import guidance 또는 wrapper
   - TypeScript props와 React 18/19 호환성
   - package `exports`, `types`, `style.css`, `dist` 산출물
4. `kraddr-geo-ui` 특화 기능은 이 저장소에서 구현한다.
   - geocode/reverse/debug form과 지도 click 결과 연결
   - API 응답 좌표/주소/정합성 sample overlay
   - VWorld key 미설정 시 이 프로젝트의 좌표 preview fallback 문구와 layout
   - transient tile error를 이 프로젝트의 debug UX에 맞게 표시하는 overlay 임계치
   - 관리 UI 상태, benchmark, load/consistency 결과와 지도 연결
5. upstream 수정이 필요하면 test/build를 통과시킨 뒤 PR을 올린다.
6. `python-kraddr-geo`에서 dependency를 검증된 최신 upstream commit 또는 release로 갱신한다.
7. `kraddr-geo-ui`의 `CoordinateMap`은 upstream component/hook과 이 저장소 domain wrapper의 경계를 명확히 한다.
8. `kraddr-geo-ui`에서 `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 수행한다.
9. Playwright 또는 브라우저 검증이 가능한 환경에서는 `/debug/geocode`, `/debug/reverse`에서 지도 표시, marker 이동, click reverse 입력, tile error/fallback 상태를 확인한다.

### 결과 기준

T-044 완료 조건:

- `kraddr-geo-ui/lib/vworld.ts`는 upstream public API 재수출 또는 아주 얇은 alias만 유지한다.
- `CoordinateMap.tsx`는 domain wrapper가 되고, MapLibre primitive lifecycle은 upstream으로 이동한다. 단, 이 프로젝트의 주소 디버그/관리 UI 특화 동작은 wrapper에 남긴다.
- upstream에 필요한 수정이 있었다면 `digitie/maplibre-vworld-js` PR/commit 링크와 검증 결과를 `docs/frontend-package.md`, `docs/journal.md`, PR 본문에 남긴다.
- `python-kraddr-geo` PR만으로 해결할 수 없는 upstream 이슈는 TODO로 남기지 않고, 최소한 upstream issue/PR 또는 별도 branch 작업으로 추적한다.

### 위험과 제약

- 지도 컴포넌트는 브라우저/WebGL 의존성이 강하므로 SSR 단계 import가 다시 생기면 Next.js build 또는 hydration에서 깨질 수 있다.
- VWorld API key는 브라우저 노출 키이지만 저장소와 PR 본문에 평문으로 남기지 않는다.
- upstream SHA 또는 release 갱신은 lockfile `resolved`가 `git+https`인지 확인한다. CI는 SSH key 없이 설치되어야 한다.
- `maplibre-vworld-js`가 npm stable release를 제공하기 전까지는 최신 `main` GitHub SHA 고정과 소비자 build 검증을 함께 기록한다.

---

## ADR-029: 원천 자료 기준월은 source set으로 명시하고 혼합 적재는 확인 절차를 거친다

- 상태: accepted (T-045 구현 완료)
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

### 컨텍스트

도로명주소 한글 정본, 위치정보요약DB, 내비게이션용DB, 전자지도 SHP, 도로명주소 출입구 정보, 상세주소/구역 추가 레이어는 업데이트 주기가 다를 수 있다. 실제 로컬 검증에서도 도로명주소 한글 정본은 `202603`, 위치정보요약DB/내비게이션용DB/SHP는 `202604`, direct 출입구 자료는 `202605`처럼 서로 다른 기준월을 갖고 있었다.

기존 CLI 예시는 `kraddr-geo load all-sidos ... --yyyymm 202604`처럼 단일 기준월을 모든 child에 적용하는 형태였다. 이 방식은 실제 원천 월을 덮어써 감사 추적을 흐리게 만들 수 있고, 운영자가 의도적으로 최신 보조 자료를 섞은 것인지 실수로 다른 월의 자료를 고른 것인지 구분하기 어렵다.

또한 `/admin/load` UI는 대용량 자료를 다룬다. 업로드가 끝나기 전에 적재를 시작하면 실패 복구가 어렵고, 사용자는 업로드 진행률과 실제 적재 진행률을 구분해서 볼 수 없다.

### 결정

원천 묶음은 단일 `yyyymm`이 아니라 `source_set` 계획 객체로 표현한다. `source_set`은 원천별 기준월, 경로, checksum, 기준월 불일치 여부, 사용자 확인 여부를 함께 가진다.

1. 기준월 필드는 원천별로 분리한다. 예: `juso_yyyymm`, `parcel_link_yyyymm`, `locsum_yyyymm`, `navi_yyyymm`, `shp_yyyymm`, `roadaddr_entrance_yyyymm`, `sppn_makarea_yyyymm`.
2. CLI는 source set의 기준월이 서로 다르면 기본적으로 멈춘다. 대화형 실행에서는 원천별 기준월 표를 보여 주고, 사용자가 지정 문구를 입력해야 계속한다.
3. 비대화형 CLI, cron, CI는 prompt를 띄우지 않는다. 혼합 기준월을 허용하려면 `--allow-mixed-yyyymm`와 명시 confirmation token 또는 문구를 함께 줘야 한다.
4. API와 라이브러리는 사용자에게 묻지 않는다. 대신 디렉터리를 읽어 후보를 매칭하는 함수와, 각 원천 기준월/경로를 명시해 적재 계획을 만드는 함수를 분리한다.
5. UI는 다중 파일 선택과 drag and drop 업로드를 지원한다. 모든 파일이 서버에 저장되고 source set 분석이 끝난 뒤에만 적재를 시작할 수 있다.
6. UI에서 source set 기준월이 맞지 않으면 팝업으로 원천별 기준월을 보여 주고, 사용자가 의도한 혼합 적재인지 확인해야 한다.
7. 업로드 진행률과 적재 진행률은 별도 퍼센트로 표시한다. 업로드는 개별 파일/전체 upload set 단위로 취소 가능해야 하고, 적재는 root `full_load_batch` job cancel로 취소해야 한다.

### API/함수 경계

라이브러리와 REST 표면은 다음 세 단계를 분리한다.

1. 발견: `discover_load_sources(root_path | upload_set_id)`는 디렉터리 또는 업로드 묶음을 읽고 `SourceSetDiscovery`를 반환한다. 이 단계는 적재하지 않는다.
2. 계획: `build_full_load_source_set_plan(...)`은 원천별 기준월 또는 명시 경로를 받아 `SourceSetPlan`을 만든다. 기준월이 섞였는데 확인 정보가 없으면 실패한다.
3. 등록: `submit_full_load_source_set(plan)` 또는 기존 `POST /v1/admin/loads kind=full_load_batch`가 확정된 plan의 child payload를 큐에 등록한다.

REST는 `/v1/admin/load-sources/discover`, `/v1/admin/load-sources/plan`, `/v1/admin/uploads/*`, `/v1/admin/loads`로 나눈다. `/v1/admin/loads`는 prompt나 파일 발견을 수행하지 않고 확정된 payload만 받는다.

### 근거

- 실제 배포 주기 차이를 데이터 모델이 숨기지 않고 드러낸다.
- C10 정합성 결과가 "실수로 섞임"과 "운영자가 승인한 혼합 적재"를 구분할 수 있다.
- CLI는 운영자가 터미널에서 바로 판단할 수 있고, API/라이브러리는 자동화에 맞게 구조화된 warning과 plan을 반환한다.
- 대용량 업로드와 적재를 분리하면 네트워크 실패, 파일 누락, 기준월 mismatch를 DB 적재 시작 전에 발견할 수 있다.

### 결과 기준

- `load_jobs.payload.source_set`, `load_jobs.source_set`, `load_manifest.source_set`, `load_consistency_reports.source_set`에는 원천별 기준월과 확인 여부가 남아야 한다.
- `mixed_yyyymm=True`이면서 `mixed_yyyymm_acknowledged=False`인 batch는 등록 또는 C10에서 차단되어야 한다.
- UI의 `/admin/load` 상태 머신은 `idle → uploading → source_review → plan_ready → processing → finished`와 `cancelled`/`failed` 전이를 표현할 수 있어야 한다. 혼합 기준월 확인은 `source_review` 단계의 modal로 처리한다.
- 업로드 파일은 저장 완료 전에는 운영 원천으로 취급하지 않는다. partial file은 `*.part`로 저장하고, checksum 확인 후 atomic rename한다.

### 후속

- (done) T-045에서 DTO, CLI, REST, UI를 구현했다.
- (open) C10 정합성 SQL/리포트가 acknowledged mixed source set을 `INFO` 또는 `WARN`으로 표현하도록 보강한다.
- (open) 기존 `load all-sidos --yyyymm`는 새 `load full-set` 명시 기준월 모드로 대체하거나 deprecated 안내를 추가한다.

---

## ADR-030: 적재 완료 DB 백업/복원은 병렬 directory dump와 압축 아카이브로 수행한다

- 상태: accepted (T-046 1차 구현 완료)
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

### 컨텍스트

전국 전체 데이터를 처음부터 적재하면 텍스트 정본, SHP 대형 레이어, 링크 해소, MV refresh/swap, C1~C10 정합성 검증까지 수 시간 단위가 걸린다. 운영자는 검증이 끝난 DB 상태를 빠르게 보존하고, 장애나 재설치 뒤에는 원천 전체를 다시 적재하지 않고 복원할 수 있어야 한다.

plain SQL 또는 DDL 중심 dump는 대용량 운영 DB에서 현실적인 기본값이 아니다. 단일 `.sql` 스트림은 파일이 커지고 복원 병렬성이 약하며, PostGIS index와 MV data가 큰 DB에서 복구 시간이 길어진다. 반대로 Docker volume snapshot이나 `pg_basebackup` 같은 물리 백업은 빠를 수 있지만 PostgreSQL cluster와 파일시스템에 강하게 묶이므로 단일 DB 이식성이 낮다.

UI 요구사항도 있다. 백업/복원은 오래 걸리므로 요청-응답으로 묶지 않고 백그라운드 작업으로 실행해야 하며, 진행률, 취소, 완료 callback, 다운로드 링크가 필요하다.

### 결정

T-046의 기본 백업 형식은 `pg_dump -Fd --jobs <N>` directory format dump를 임시 디렉터리에 만든 뒤, `manifest.json`, checksum, job log와 함께 `tar.zst` 단일 압축 아카이브로 저장하는 방식으로 한다. 복원은 archive를 해제하고 `pg_restore -Fd --jobs <N>`로 새 빈 DB에 수행한다.

T-047 전국 DB 실측 보정: `pg_dump -Fd` directory 내부의 대형 table data는 이미 `.dat.gz`로 압축되어 있어 `tar.zst` 포장 단계의 추가 압축률은 매우 작았다. dump directory 4,313,361,824 bytes가 archive 4,308,457,630 bytes가 되어 약 4.9MiB만 줄었다. 따라서 이 ADR의 `tar.zst`는 압축률보다 단일 artifact 보관, UI 다운로드, checksum 검증을 단순화하기 위한 포장 형식으로 해석한다.

세부 결정:

1. 운영 기본값은 `directory_tar_zstd`다. `pg_dump -Fp` plain SQL은 디버깅 목적 외에는 사용하지 않는다.
2. 백업 profile은 `serving-ready`, `lean-serving`, `forensic`으로 나눈다. 기본 `serving-ready`는 `mv_geocode_target` data를 포함해 복원 직후 조회가 가능해야 한다.
3. 백업/복원 작업 kind는 `db_backup`, `db_restore`로 둔다. 초기 구현은 기존 `load_jobs` 기반 영속 큐를 재사용하되, REST 표면은 중립 alias `/v1/admin/jobs/*`를 우선 사용한다.
4. 백업 파일은 사용자가 지정한 서버 측 allowlist 하위 경로에 저장한다. 브라우저 로컬 경로를 직접 쓰지 않는다.
5. callback URL은 allowlist host만 허용한다. T-046 1차 구현은 terminal state(`done`, `failed`, `cancelled`)에서 1회 delivery를 시도하고, callback 실패는 백업/복원 성공 여부와 별도로 `callback_state`에 기록한다. 제한 횟수 재시도와 backoff는 후속 hardening에서 추가한다.
6. UI는 `/admin/backups` 페이지를 추가한다. 백업 생성, 진행 중 작업, 백업 목록, 복원 탭을 제공하고, 완료된 artifact에는 다운로드 링크를 표시한다.
7. 복원은 기본적으로 새 빈 DB에만 허용한다. 현재 운영 DB를 덮어쓰는 `replace_current`는 maintenance mode, typed confirmation, 선행 백업, rollback plan을 요구하는 별도 위험 경로로 둔다.

### 보안과 운영 규칙

- `KRADDR_GEO_BACKUP_ALLOWED_DIRS` 하위 resolve path만 허용한다. `..`, symlink escape, absolute path 우회는 거절한다.
- 임시 파일은 `.part` archive 또는 임시 디렉터리에 쓰고, checksum 계산 후 최종 archive 경로로 rename한다.
- 백업 파일은 기본 `0600` 권한으로 만든다.
- 다운로드 endpoint는 내부망 전용이어도 artifact id와 token을 모두 요구한다.
- callback payload에는 DB password, DSN, API key를 넣지 않는다.
- 동시에 실행 중인 `full_load_batch`, `mv_refresh`, `db_restore`가 있으면 `db_backup` preflight에서 경고 또는 실패한다. `db_restore`는 다른 대형 job과 동시에 실행하지 않는다.

### 검증 기준

구현 첫 검증은 전국 full-load가 아니라 대구광역시 부분 적재 DB로 수행한다.

1. 빈 DB `kraddr_geo_t046_daegu`에 대구 `juso`, `parcel_link`, `locsum`, `navi`, `shp`만 적재한다.
2. `resolve_text_geometry_links()`와 `refresh mv --swap` 후 row count와 geocode/reverse smoke test를 확인한다.
3. `db_backup`으로 `.tar.zst` artifact를 만들고, manifest/checksum/callback/download link를 검증한다.
4. 새 빈 DB `kraddr_geo_t046_daegu_restore`에 `db_restore`를 실행한다.
5. 원본/복원 DB의 핵심 row count, `mv_geocode_target`, 대구 geocode/reverse smoke test가 일치하는지 확인한다.

### 결과

- 운영자는 검증 완료 DB를 압축 artifact로 보존할 수 있다.
- 재검증과 재설치 복구가 원천 full-load보다 훨씬 빠른 경로를 갖는다.
- 백업/복원 작업도 `load_jobs`와 같은 관측·취소·복구 규칙을 따른다.
- logical dump라 물리 snapshot보다 느릴 수 있지만 DB 단위 이식성과 리뷰 가능한 manifest를 얻는다.

### 구현 결과

- T-046에서 DTO, API router, job handler, CLI, UI를 구현했다.
- 백업 metadata는 `ops.artifacts(artifact_type='db_backup')`에 저장한다. 복원 실행 로그는 `ops.artifacts(artifact_type='db_restore_log')`에 저장한다.
- `pg_dump`/`pg_restore` command builder는 DSN password를 argv에서 제거하고 `PGPASSWORD` 환경변수로 주입한다. 로그용 command도 password를 포함하지 않는다.
- `KRADDR_GEO_BACKUP_ALLOWED_DIRS`와 `KRADDR_GEO_BACKUP_CALLBACK_ALLOWED_HOSTS`는 문서 예시처럼 comma-separated env 값을 받을 수 있도록 `NoDecode` + validator로 처리한다.
- 대구광역시 부분 적재 DB `kraddr_geo_t046_daegu`를 `t046_daegu_backup.tar.zst`로 백업하고, `kraddr_geo_t046_daegu_restore`에 복원해 row count와 geocode/reverse smoke test를 비교했다.

### 후속

- (open) callback retry/backoff와 delivery attempt audit를 추가한다.
- (open) restore 취소 시 target DB drop/quarantine 정책을 구현한다.
- (open) 디스크 여유 공간 사전 추정과 PostgreSQL/PostGIS major mismatch hard-fail 정책을 추가한다.
- (open) 같은 호스트 초고속 재해복구가 필요하면 물리 snapshot 전략을 별도 ADR로 검토한다.

---

## ADR-031: 전국 적재 후 쿼리 성능은 반복 벤치마크로 gate하고 보조 view/MV 도입을 허용한다

- 상태: accepted (T-047 1차 harness와 지번 exact 튜닝 완료)
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

### 컨텍스트

T-033~T-035는 full-load, SHP 적재, MV refresh/swap 성능을 다뤘다. 그러나 운영 사용자가 직접 체감하는 지표는 적재 시간이 아니라 지오코딩, 역지오코딩, 통합 검색의 응답 latency다. 전국 전체 데이터가 적재된 뒤에는 row count, 데이터 분포, 도시 밀도, fuzzy 후보 수, 공간 index 선택성이 작은 샘플과 다르므로 실제 운영 규모에서 다시 측정해야 한다.

정합성이 맞아도 p95/p99 latency가 높으면 운영 준비가 끝난 것이 아니다. 특히 주소 검색은 대화형 UI와 API 호출 경로에서 반복 실행되므로 tail latency와 timeout이 중요하다.

### 결정

T-047에서는 전국 full-load 직후 query benchmark를 별도 품질 gate로 둔다. 최소 query군은 도로명 exact, 지번 exact, fuzzy geocode, 통합 search, reverse nearest, reverse radius, zipcode lookup, no-result/invalid 경로다. 각 query군은 p50, p90, p95, p99, max, timeout, error rate, buffer 사용량, plan hash를 기록한다.

성능 목표를 초과하는 query군은 인덱스 추가, SQL 재작성, query split, `UNION ALL` 분기, KNN 후보 추출, 5179 공간 index 사용 보강을 먼저 실험한다. 이것만으로 부족하면 `mv_geocode_target` 또는 master table에서 파생된 read-only 보조 view/materialized view를 적극 도입할 수 있다.

허용되는 보조 객체 예:

- `mv_geocode_exact_key`: 도로명/지번 exact lookup 전용 slim MV
- `mv_geocode_text_search`: fuzzy/search 전용 정규화 text/trgm MV
- `mv_reverse_point_5179`: reverse/radius 전용 point-only slim MV
- `mv_zipcode_lookup`: zipcode lookup 전용 MV
- `v_admin_boundary_4326`: 디버그/지도 표시용 polygon 변환 view
- `mv_sppn_reverse_area`: T-042 이후 국가지점번호 표기 의무지역 reverse 보조 MV

### 제약

- 보조 view/MV는 source of truth가 아니다. master table 또는 `mv_geocode_target`에서 재생성 가능한 read-only serving accelerator여야 한다.
- API 응답 구조와 vworld 호환 계약은 바꾸지 않는다. 자체 확장은 계속 `x_extension` 안에만 둔다.
- `pg_trgm.similarity_threshold` 전역 변경은 금지한다. 필요하면 transaction 단위 `SET LOCAL`만 사용한다.
- 공간 쿼리는 입력 좌표를 한 번만 5179로 변환하고, indexed geometry column에는 `ST_Transform`을 걸지 않는다.
- 보조 MV를 도입하면 refresh/swap 순서, index build time, disk size, `ANALYZE`, T-046 backup/restore 영향까지 함께 기록한다.
- 튜닝 PR은 "변경 전/후 p95/p99, plan, buffer, 부작용" 표 없이는 merge하지 않는다.

### 측정 기준

초기 목표는 다음과 같다. 실제 하드웨어와 corpus가 확정되면 T-047 결과 문서에서 조정할 수 있다.

| 쿼리군 | DB p95 목표 | REST p95 목표 |
|--------|------------:|--------------:|
| 도로명 exact geocode | 30ms 이하 | 100ms 이하 |
| 지번 exact geocode | 30ms 이하 | 100ms 이하 |
| fuzzy geocode | 150ms 이하 | 300ms 이하 |
| 통합 search | 150ms 이하 | 300ms 이하 |
| reverse nearest | 50ms 이하 | 150ms 이하 |
| reverse radius | 100ms 이하 | 250ms 이하 |
| zipcode lookup | 30ms 이하 | 100ms 이하 |
| no-result/invalid | 50ms 이하 | 150ms 이하 |

목표를 초과하면 최소 10개 이상의 후보 실험을 수행하고, 각 실험은 결과가 실패해도 artifact와 report에 남긴다.

### 결과

- 운영 latency가 감각이 아니라 수치와 plan으로 관리된다.
- 추가 view/MV/index를 도입해도 source of truth와 응답 계약을 지킬 수 있다.
- 성능 개선이 적재/refresh/backup 비용을 얼마나 늘리는지 함께 판단할 수 있다.
- T-027 최종 클린 로드 이후 T-047 benchmark가 운영 준비의 다음 gate가 된다.

### 후속

- (done) T-047 1차 PR에서 benchmark harness, corpus JSON, summary/report artifact schema를 구현했다.
- (done) T-027 최종 full-load DB에서 smoke와 small concurrency baseline을 측정하고 `idx_mv_jibun_name_exact`를 추가했다.
- (open) 목표 초과 query군은 trial별로 index/query/view/MV 후보를 실험한다.
- (open) 최종 채택한 보조 object는 `docs/data-model.md`와 Alembic migration에 반영한다.

---

## ADR-032: `maplibre-vworld-js`는 최신으로 소비하고 `kraddr-geo` 특화 기능은 이 저장소에 둔다

- 상태: accepted
- 날짜: 2026-05-27
- 결정자: 사용자 요청, codex

### 컨텍스트

ADR-020과 ADR-028은 VWorld WMTS + MapLibre GL JS 전환 과정에서 `digitie/maplibre-vworld-js`를 적극 보강 대상으로 두었다. 이 방향은 유지한다. 다만 "완전 포팅"이라는 표현은 `kraddr-geo-ui`의 지오코딩/역지오코딩 디버그 UX, 정합성 sample overlay, 적재/성능 분석 화면처럼 이 프로젝트에만 의미가 있는 기능까지 upstream package로 옮기는 것으로 오해될 수 있다.

또한 `maplibre-vworld-js`는 별도 저장소에서 빠르게 바뀌고 있다. GitHub dependency를 오래된 SHA에 고정하면 최신 upstream의 bug fix, package export, 타입 보강, marker/overlay 기능을 놓칠 수 있다. 따라서 이 저장소에서 `maplibre-vworld` 의존성을 만질 때는 항상 최신 `main` 또는 최신 stable release를 먼저 확인해야 한다.

### 결정

`kraddr-geo-ui`는 `maplibre-vworld-js`를 항상 최신 확인 버전으로 소비한다. 현재 확인된 upstream `main` 최신 커밋은 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`이며, `kraddr-geo-ui/package.json`과 lockfile은 이 SHA를 사용한다.

책임 경계는 다음과 같다.

1. `maplibre-vworld-js` 책임:
   - VWorld tile URL, layer/style helper, layer별 `maxZoom`, attribution
   - MapLibre map/marker/popup/cluster 같은 범용 primitive
   - click/error/flyTo hook처럼 다른 VWorld MapLibre 소비자도 재사용할 수 있는 component 또는 hook
   - VWorld tile error 판별, URL redaction, key 노출 방지 helper
   - package `exports`, `types`, `style.css`, `dist` 산출물, React/Next.js/Vite 호환성
   - 범용 동작의 단위 테스트와 예제
2. `python-kraddr-geo` / `kraddr-geo-ui` 책임:
   - geocode/reverse/debug/admin 화면의 입력 상태와 지도 click 결과 연결
   - API 응답 좌표, 주소 후보, 정합성 sample, 성능 benchmark 결과를 지도에 overlay하는 domain wrapper
   - `NEXT_PUBLIC_VWORLD_API_KEY` 미설정 시 이 프로젝트 UI 문맥에 맞는 좌표 preview fallback
   - transient tile error를 이 프로젝트의 디버그 UX에 맞게 몇 회까지 warning으로 볼지 결정하는 임계치와 표시 문구
   - load job, consistency report, backup/restore, query benchmark 같은 운영 콘솔 상태와 지도 상호작용

즉, upstream은 "VWorld + MapLibre를 잘 쓰기 위한 범용 도구"를 제공하고, 이 저장소는 "한국 주소 지오코딩 라이브러리의 디버깅·관리 경험"을 구현한다.

### 실행 규칙

- `maplibre-vworld` dependency를 건드리는 PR은 `git ls-remote https://github.com/digitie/maplibre-vworld-js.git refs/heads/main` 또는 최신 release 확인 결과를 문서와 PR 본문에 남긴다.
- npm registry stable release가 없거나 아직 검증 전이면 GitHub dependency는 `git+https://...#<verified-sha>` 형식으로 둔다. SSH `git@github.com:` 또는 `github:` shorthand로 lockfile이 바뀌면 CI 환경에서 key 없이 설치되지 않을 수 있으므로 되돌린다.
- 최신 upstream을 올린 뒤 `kraddr-geo-ui`에서 `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 실행한다.
- 최신 upstream에 범용 결함이 있으면 `maplibre-vworld-js` 저장소를 직접 수정한다. 이 저장소에는 장기 workaround를 쌓지 않는다.
- 프로젝트 특화 기능은 upstream PR로 보내지 않는다. 필요한 경우 `maplibre-vworld-js`에는 범용 extension point만 추가하고, 실제 주소 디버그/관리 동작은 이 저장소 wrapper에서 구현한다.
- `VWorldMap` 또는 hook으로 포팅하더라도 `CoordinateMap.tsx`는 완전히 사라질 필요가 없다. 남아 있다면 upstream primitive를 감싸는 domain wrapper여야 하며, 직접 MapLibre lifecycle을 다시 소유하지 않아야 한다.

### 결과

- 현재 `kraddr-geo-ui`는 `maplibre-vworld`를 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`로 갱신한다.
- T-044의 의미는 "모든 지도 관련 기능을 upstream으로 이동"이 아니라 "범용 지도 primitive는 upstream 최신 API로 소비하고, `kraddr-geo-ui` 특화 UX는 이 저장소에서 명확히 경계화"로 재정의한다.
- 이후 maplibre-vworld 관련 작업은 최신성 확인, 책임 경계, 양쪽 저장소 검증 결과를 함께 남긴다.

---

## ADR-033: 운영 메타데이터는 `ops` 스키마의 감사·스냅샷·릴리스 테이블로 관리한다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, codex

### 컨텍스트

T-027 이후 실제 전국 적재, T-045 source set, T-046 백업/복원, T-047 성능 튜닝이 이어지면 운영자가 추적해야 할 정보가 급격히 늘어난다. 현재 `load_jobs`, `load_manifest`, `load_consistency_reports`는 적재와 검증의 일부 상태를 담지만, 다음 질문에는 충분히 답하지 못한다.

- 현재 운영 중인 데이터셋이 어떤 source set, row count, migration revision, git commit으로 만들어졌는가?
- 어떤 정합성 리포트와 성능 리포트가 이 데이터셋의 운영 반영을 승인했는가?
- 어떤 job이 어떤 backup/export/report artifact를 만들었고, checksum과 보존 정책은 무엇인가?
- 누가 CLI/API/UI에서 위험 작업을 실행했고, 어떤 confirmation과 maintenance window 아래에서 실행했는가?
- `mv_geocode_target` swap 이후 active serving release가 무엇이고, rollback 가능한 직전 release는 무엇인가?

로그 파일과 PR 본문만으로 이 정보를 맞춰 보는 방식은 재설치, 장애 복구, 데이터 회귀 분석에서 취약하다. DB 내부에 운영 메타데이터를 구조화해서 남겨야 한다.

### 결정

운영 메타데이터 전용 `ops` 스키마를 추가한다.

```sql
CREATE SCHEMA IF NOT EXISTS ops;
```

`public`은 주소 원천·serving 테이블과 view/materialized view를 유지하고, `x_extension`은 PostGIS 보조 extension 격리 용도로 유지한다. `ops`는 운영 감사, 데이터셋 snapshot, serving release, artifact registry, maintenance window, table stats snapshot만 담는다. 애플리케이션 SQL은 `search_path`에 기대지 않고 `ops.<table>`을 명시한다.

T-049 구현에서 다음 테이블을 추가했다.

| 테이블 | 목적 |
|--------|------|
| `ops.audit_events` | 관리 작업과 위험 작업의 append-only 감사 이벤트. actor, request/trace id, action, resource, outcome, redacted payload hash를 저장 |
| `ops.dataset_snapshots` | full-load, daily delta, restore 후 검증 가능한 데이터셋 상태. source set, row count, consistency/performance/backup artifact, code/schema version을 연결 |
| `ops.serving_releases` | 어떤 snapshot이 현재 운영 조회 release인지 기록. active release 1건 강제, rollback lineage 보존 |
| `ops.artifacts` | backup, restore log, consistency export, performance report, source inventory, schema diff 등 운영 산출물의 공통 registry |
| `ops.maintenance_windows` | restore, schema migration, full-load, MV swap 같은 위험 작업의 의도된 maintenance 상태와 차단 규칙 |
| `ops.table_stats_snapshots` | 테이블/MV/index row count, size, bloat, analyze 상태를 시간축으로 기록 |

T-046에서 계획한 `db_backup_artifacts`는 신규 구현에서는 `ops.artifacts`의 `artifact_type='db_backup'`으로 수렴한다. 이미 별도 테이블이 생성된 배포가 있다면 compatibility view 또는 migration으로 흡수한다.

### 규칙

- `ops.audit_events`는 append-only다. 운영자가 삭제해야 하는 경우에도 삭제 row를 남기거나 archive 상태로 전환한다.
- `ops.audit_events.job_id`는 `load_jobs(job_id)`를 참조하되 `ON DELETE NO ACTION`으로 둔다. 감사 이벤트가 있는 job을 삭제하면 job id 연결이 사라지므로, `ON DELETE SET NULL`로 조용히 끊지 않고 정리 정책을 명시하도록 DB가 차단한다.
- API key, DSN password, callback secret, download token, 외부 API key는 어떤 `ops` 테이블에도 평문 저장하지 않는다.
- 주소 원문은 관리 작업 근거에 꼭 필요한 경우에도 마스킹 또는 hash를 우선한다. 검색 API 요청 전체를 감사 테이블에 저장하지 않는다.
- active serving release는 DB constraint로 한 건만 허용한다.
- destructive restore, 운영 DB overwrite, schema migration, full reset은 active maintenance window와 typed confirmation 없이는 실패한다.
- backup, consistency report, performance report, data-quality export는 가능하면 `ops.artifacts`에 등록하고 checksum을 검증한다.
- snapshot은 source set hash, row count, Alembic revision, git commit, PostgreSQL/PostGIS version을 포함해야 한다.
- T-047 성능 튜닝에서 보조 MV/index를 추가하면 table stats snapshot과 serving release metadata에도 영향이 기록되어야 한다.

### API와 UI

REST 표면은 `/v1/admin/ops/*`를 기본으로 둔다.

- `GET /v1/admin/ops/snapshots`
- `GET /v1/admin/ops/releases`
- `POST /v1/admin/ops/releases/{release_id}/rollback-plan`
- `GET /v1/admin/ops/artifacts`
- `GET /v1/admin/ops/audit-events`
- `GET /v1/admin/ops/maintenance-windows`
- `POST /v1/admin/ops/maintenance-windows`
- `POST /v1/admin/ops/maintenance-windows/{window_id}/end`
- `GET /v1/admin/ops/table-stats`
- `POST /v1/admin/ops/table-stats/capture`

프론트엔드는 `/admin/ops` 또는 기존 `/admin/load`, `/admin/backups`, `/admin/consistency` 내부 탭에서 시작한다. 첫 UI는 active release, 최근 snapshot, artifact 목록, maintenance window 상태, 주요 table/MV size를 보여 주면 충분하다.

### 근거

- `load_jobs`는 실행 상태, `ops.audit_events`는 운영 의사결정 이력을 담당하게 되어 역할이 분리된다.
- snapshot과 release를 분리하면 "검증된 데이터셋"과 "현재 운영 조회에 노출된 데이터셋"을 혼동하지 않는다.
- artifact registry를 공통화하면 T-046 백업 파일, T-047 성능 리포트, C2/C4/C6/C7 data-quality export가 같은 보존·checksum·download 규칙을 따른다.
- maintenance window를 DB에 두면 CLI, API, UI, background worker가 같은 차단 규칙을 공유한다.

### 결과

- T-049 구현 PR에서 `ops` 스키마 DDL, Alembic `0006_t049_ops_metadata_schema`, DTO/API/client/UI, redaction/hash helper, append-only audit trigger, active release partial unique index, table stats snapshot capture를 추가했다.
- `docs/t049-ops-metadata-schema.md`에 구현 상태와 남은 연결점을 둔다.
- T-045/T-046/T-047 구현 시 source set 확정, backup/restore artifact, performance report, MV swap gate를 snapshot/artifact/release에 실제로 연결한다.

---

## ADR-034: AI 에이전트는 고정 Git worktree와 CodeGraph 인덱스를 사용한다

- 상태: accepted
- 날짜: 2026-05-27
- 결정자: 사용자 요청, codex

### 컨텍스트

이 프로젝트는 ChatGPT Codex, Claude Code, Google Antigravity 2.0 같은 여러 AI 에이전트가 같은 저장소를 이어서 작업하는 방식 자체도 검증 대상이다. 지금까지는 같은 checkout에서 branch를 바꾸거나, 새 세션이 임시 위치에서 작업을 시작하는 일이 있었다. 이 방식은 다음 문제를 만든다.

- 에이전트가 다른 에이전트의 미커밋 변경을 덮어쓸 위험이 있다.
- branch 전환과 PR rebase가 같은 작업 디렉터리에서 겹치면 현재 작업의 소유자가 불분명해진다.
- CodeGraph 같은 로컬 인덱스가 checkout 단위로 만들어질 때, 어느 에이전트가 어느 인덱스를 갱신해야 하는지 애매하다.
- Windows 재설치나 새 Codex 세션 후 `git pull`만으로 작업을 복구하려면 worktree 이름과 branch 생성 규칙이 문서화되어 있어야 한다.

CodeGraph 원문 문서는 `codegraph init -i`가 프로젝트의 `.codegraph/` 디렉터리를 만들고 전체 인덱스를 즉시 생성하며, 기존 프로젝트는 `codegraph sync`로 증분 갱신할 수 있다고 설명한다. `.codegraph/`는 로컬 SQLite 지식 그래프이므로 저장소 이력에 넣을 대상이 아니다.

### 결정

WSL ext4의 `~/dev` 아래에 에이전트별 고정 Git worktree를 둔다.

| 에이전트 | 고정 worktree | branch prefix |
|----------|---------------|---------------|
| ChatGPT Codex | `~/dev/geo-codex` | `agent/codex-*` |
| Claude Code | `~/dev/geo-claude` | `agent/claude-*` |
| Google Antigravity 2.0 | `~/dev/geo-antigravity` | `agent/antigravity-*` |

기준 clone(`~/dev/python-kraddr-geo`)은 `main` 동기화와 worktree 관리용으로 둔다. 실제 작업은 각 에이전트의 고정 worktree에서 수행하고, 작업마다 새 branch만 만든다. worktree 자체를 작업마다 삭제하거나 재생성하지 않는다.

최초 1회 생성 절차:

```bash
cd ~/dev/python-kraddr-geo
git fetch origin main
git worktree add ../geo-codex -b agent/codex-worktree origin/main
git worktree add ../geo-claude -b agent/claude-worktree origin/main
git worktree add ../geo-antigravity -b agent/antigravity-worktree origin/main
```

새 작업 시작 절차:

```bash
cd ~/dev/geo-codex
git status --short
git fetch origin main
git switch -c agent/codex-next origin/main
codegraph sync
```

로컬 `main`이 최신으로 fast-forward된 것이 확인된 경우 사용자 예시처럼 다음 축약형도 가능하다.

```bash
git fetch
git switch -c agent/codex-next main
codegraph sync
```

다만 자동화와 AI 에이전트는 여러 worktree가 `main` checkout을 동시에 요구하지 않도록 `origin/main`을 시작점으로 쓰는 절차를 기본으로 한다.

CodeGraph는 worktree마다 최초 1회만 초기화한다.

```bash
codegraph init -i
```

`.codegraph/`가 이미 있으면 재초기화하지 않고 다음 명령으로 유지한다.

```bash
codegraph sync
codegraph status
```

프로젝트 루트의 `.codex/config.toml`에는 CodeGraph MCP stdio 서버를 등록한다.

```toml
[mcp_servers.codegraph]
enabled = true
command = "codegraph"
args = ["serve", "--mcp"]
```

`codegraph install --print-config codex`가 제안하는 로컬 CLI 방식이 WSL ext4 개발 환경의 기본값이다. Node/npm만 사용하는 환경에서는 `npx -y @colbymchenry/codegraph mcp` 형태를 쓸 수 있으나, WSL에서 Windows npm shim이 먼저 잡히면 UNC 경로 문제가 생길 수 있으므로 이 저장소는 standalone `codegraph` 실행 파일을 우선한다.

Codex Desktop을 재시작해 MCP가 노출된 세션에서는 `kraddr-geo-ui` 컴포넌트, 지도 wrapper, 공용 UI primitive, `maplibre-vworld-js` 소비 경계를 수정하기 전에 반드시 CodeGraph MCP의 `codegraph_explore`로 영향도를 확인한다. 최소 확인 범위는 호출자, props/type 공유 지점, 관련 테스트, upstream으로 옮길 수 있는 범용 기능과 이 저장소에 남길 domain wrapper 기능이다.

`.codegraph/`는 `.gitignore`에 추가한다.

### 근거

- 고정 worktree는 에이전트별 파일 시스템 상태와 Git index를 분리하므로 미커밋 변경 충돌을 줄인다.
- 작업마다 branch만 새로 만들면 PR, commit, merge 이력이 작고 추적 가능하다.
- CodeGraph 인덱스를 worktree 단위로 유지하면 에이전트가 자기 checkout의 현재 branch를 기준으로 탐색한다.
- MCP의 `codegraph_explore`를 컴포넌트 수정 전 표준 절차로 두면 UI 변경의 호출자·테스트·upstream 경계를 놓칠 가능성을 줄인다.
- `.codegraph/`를 ignore하면 로컬 SQLite DB, watcher 상태, 인덱스 재생성 산출물이 리뷰 diff에 섞이지 않는다.
- `origin/main`을 시작점으로 쓰면 `main` branch가 다른 worktree에서 checkout되어 있어도 새 작업 branch를 만들 수 있다.

### 결과

- `docs/dev-environment.md`와 `docs/agent-guide.md`에 worktree 생성, 새 branch 시작, CodeGraph 초기화/동기화 절차를 추가한다.
- 프로젝트 루트 `.codex/config.toml`에 CodeGraph MCP stdio 서버 설정을 추가한다.
- 컴포넌트 수정 전 `codegraph_explore` 영향도 평가를 에이전트 작업 규칙으로 추가한다.
- `AGENTS.md`, `SKILL.md`, `README.md`에 핵심 정책을 요약한다.
- `.gitignore`에 `.codegraph/`를 추가한다.
- 새 에이전트 세션은 작업 전 자기 worktree와 CodeGraph 상태를 먼저 확인한다.
- 이번 작업에서 실제로 `~/dev/geo-codex`, `~/dev/geo-claude`, `~/dev/geo-antigravity` worktree를 만들고, 각 worktree에서 `codegraph init -i`와 `codegraph status`를 실행했다.

### 남은 위험

- CodeGraph CLI가 Windows npm shim만 PATH에 있고 WSL Node가 없으면 `codegraph` 실행이 실패할 수 있다. WSL에서는 Linux installer 또는 Linux Node/npm 기반 설치를 우선한다.
- 이미 존재하는 worktree에 미커밋 변경이 있으면 새 작업 branch를 만들기 전에 해당 에이전트가 변경의 소유권을 확인해야 한다.
- 장기 실행 중인 PR branch가 merge되기 전에 같은 worktree에서 다음 branch를 만들면 변경 추적이 흐려진다. PR이 머지되거나 명시 보류된 뒤 새 branch를 시작한다.

---

## ADR-021: 도로명주소 일변동 ZIP은 MST만 즉시 반영하고 LNBR은 manifest에 기록한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-028 구현

### 컨텍스트

행안부 도로명주소 일변동 ZIP(`daily/*.zip`)에는 `TH_SGCO_RNADR_MST.TXT`와 `TH_SGCO_RNADR_LNBR.TXT`가 함께 들어 있다. `MST` member는 기존 `rnaddrkor_*.txt`와 같은 건물 단위 도로명주소 정본 구조에 `MVM_RES_CD`가 추가된 형태라 현재 `tl_juso_text`에 바로 반영할 수 있다. 반면 `LNBR` member는 건물관리번호와 지번의 보조 관계를 제공하므로 현재 `tl_juso_text`의 대표 지번 1개 모델과 직접 맞지 않는다.

### 결정

T-028 daily loader는 `TH_SGCO_RNADR_MST.TXT`만 `tl_juso_text`에 적용한다.

- `31`, `33`은 UPSERT한다.
- `34`, `35`, `36`도 UPSERT한다.
- `63`, `64`는 `bd_mgt_sn` 기준 DELETE한다.
- 알 수 없는 `MVM_RES_CD`는 skip하지 않고 `LoaderError`로 중단한다.
- 같은 batch 안에 동일 `bd_mgt_sn`이 여러 번 나오면 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 1건만 master에 반영한다.
- `TH_SGCO_RNADR_LNBR.TXT`는 T-028 daily MST loader에서 master에 쓰지 않고 행 수만 `DailyJusoLoadResult.unsupported_lnbr_rows`와 `load_manifest.source_set.unsupported_lnbr_rows`에 기록한다. T-038 이후 실제 LNBR 반영은 `juso_parcel_link_delta`가 담당한다.
- `LNBR` 및 `jibun_rnaddrkor_*`의 1:N 지번 관계 테이블 여부는 ADR-022에서 결정한다.

### 근거

- `MST`는 기존 `parse_juso_row()`와 PNU generated column을 재사용할 수 있어 full-load 정본과 같은 컬럼 의미를 유지한다.
- daily ZIP을 재실행해도 결과가 같아야 하므로 신규/수정은 모두 UPSERT가 안전하다.
- 운영 DB의 full-load 기준월과 daily ZIP 기준일이 어긋날 수 있으므로 `update` 코드가 기존 행을 찾지 못해도 실패시키지 않는다.
- `LNBR`을 현재 `tl_juso_text`에 덮어쓰면 대표 지번이 어떤 기준으로 선택되었는지 불명확해진다. 조용한 손실보다 명시적 미지원 기록이 낫다.

### 결과

- CLI는 `kraddr-geo load daily-juso <zip-or-dir>`를 제공한다.
- API 작업 큐는 `kind="daily_juso_delta"`를 제공한다.
- `load_manifest.last_delta_at`, `last_mvmn_de`, `source_checksum`, `source_set`이 daily 적용 watermark 역할을 한다.
- T-027 최종 클린 적재에서는 full-load 뒤 daily ZIP 일부 적용을 별도 smoke로 추가할 수 있다.

### 남은 위험

- 여러 날짜 ZIP을 디렉터리로 한 번에 적용할 때 파일명 정렬에 의존한다. 현재 로더는 최종 반영 시 `mvmn_de`와 `staging_seq`로 최신 상태를 고르지만, 제공자가 같은 날짜 안에서 더 세밀한 순서를 제공하면 그 필드를 추가로 반영해야 한다.
- `LNBR` 반영은 T-038 `juso_parcel_link_delta`로 분리됐다. 다만 이 테이블을 지번 검색 후보에 연결하는 작업은 아직 후속이다.

---

## ADR-022: 보조 지번 원천은 `tl_juso_text`가 아니라 1:N 링크 테이블로 모델링한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-029 실제 파일 검토

### 컨텍스트

도로명주소 한글 전체분에는 `rnaddrkor_*.txt`와 함께 `jibun_rnaddrkor_*.txt`가 배포된다. T-028 daily ZIP에는 같은 성격의 `TH_SGCO_RNADR_LNBR.TXT` member가 있다. 두 파일은 모두 건물관리번호와 지번을 연결하지만, 현재 `tl_juso_text`는 한 건물 행에 대표 지번 1개만 보관한다.

실제 파일 계측 결과 이 원천들은 대표 지번 보정용이 아니라 보조 지번 1:N 관계다.

- 전국 `jibun_rnaddrkor_*`: 1,769,370행, distinct `bd_mgt_sn` 986,309, 2개 이상 보조 지번을 가진 건물 334,789건, 한 건물 최대 545행.
- 서울 `jibun_rnaddrkor_seoul.txt`: 89,290행, distinct `bd_mgt_sn` 52,280, 2개 이상 보조 지번을 가진 건물 13,318건.
- 서울 `jibun_rnaddrkor` PNU와 `rnaddrkor` 대표 PNU 비교: 89,290행 중 89,289행이 대표 PNU와 다르다.
- daily `20260401` LNBR: 204행, distinct `bd_mgt_sn` 72, 2개 이상 변경 지번을 가진 건물 31건, 코드 분포 `31=74`, `63=130`.

### 결정

`jibun_rnaddrkor_*`와 daily `LNBR`는 `tl_juso_text.pnu`에 덮어쓰지 않는다. T-038에서 별도 테이블 `tl_juso_parcel_link`를 만든다.

구현된 테이블의 핵심:

- PK: `(bd_mgt_sn, pnu)`
- 주요 컬럼: `bd_mgt_sn`, `pnu`, `bjd_cd`, `mntn_yn`, `lnbr_mnnm`, `lnbr_slno`, `sig_cd`, `rn_cd`, `buld_se_cd`, `buld_mnnm`, `buld_slno`, `source_kind`, `source_file`, `source_yyyymm`, `last_mvmn_de`
- 인덱스: `pnu`, 도로명 건물번호 키(`sig_cd`, `rn_cd`, `buld_se_cd`, `buld_mnnm`, `buld_slno`)
- `bd_mgt_sn`은 `tl_juso_text`를 참조하고 `ON DELETE CASCADE`를 사용한다.

`rnaddrkor_*.txt`에서 온 `tl_juso_text.pnu`는 계속 대표 PNU로 유지한다. `mv_geocode_target`도 지금처럼 `bd_mgt_sn` unique를 유지한다.

### 근거

- 한 건물에 보조 지번이 수백 개까지 붙을 수 있으므로 `tl_juso_text` 1행 구조에 넣으면 데이터가 손실된다.
- 대표 PNU와 보조 PNU의 의미가 다르다. 대표 PNU를 바꾸면 기존 지번 geocode와 외부 조인의 의미가 조용히 바뀐다.
- daily `LNBR`는 insert/delete movement code를 포함하므로 full snapshot과 같은 테이블에 delta를 적용할 수 있다.
- 별도 테이블을 두면 지번 검색 확장, 디버그 표시, 정합성 검증을 단계적으로 붙일 수 있고, 현행 `mv_geocode_target`의 unique 제약을 깨지 않는다.

### 결과

- T-029는 DDL/loader를 바로 만들지 않고 결정과 실제 파일 테스트만 남긴다.
- T-038에서 `tl_juso_parcel_link` DDL/Alembic, full snapshot loader, daily LNBR delta loader를 구현했다.
- T-028 `daily_juso_delta`는 MST 전용으로 남기고, 같은 ZIP의 LNBR은 T-038 `juso_parcel_link_delta`로 별도 적용한다. 이 분리는 MST와 보조 지번 delta의 실패/재시도 단위를 분리하기 위한 것이다.

### 남은 위험

- `tl_juso_parcel_link`를 지번 검색에 바로 연결하면 한 건물에 여러 지번이 매칭되며 랭킹/중복 제거 정책이 필요하다.
- `bd_mgt_sn` 길이가 원천별로 25/26자리 혼재할 가능성은 T-027 SHP에서 이미 확인했다. `jibun_rnaddrkor_*`와 `rnaddrkor_*` 사이에서는 서울 샘플 기준 모두 매칭됐지만, 전국 loader 구현 전 다시 전수 확인한다.

---

## ADR-023: 별도 도형/출입구 자료는 full-load 기본 경로에 즉시 섞지 않고 후보별로 분리한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-030 실제 파일 검토

### 컨텍스트

`data/juso`에는 현재 로더가 쓰는 월간 텍스트 3종과 도로명주소 전자지도 외에도 다음 별도 묶음이 있다.

- `건물군 내 상세주소 동 도형`
- `구역의 도형`
- `도로명주소 건물 도형`
- `도로명주소 출입구 정보`

T-027 계획에서는 이들을 미지원 입력으로 표시했다. T-030에서 세종특별자치시 실제 ZIP을 열어 layer, geometry type, DBF row count/field, text row 구조를 확인했다.

### 결정

이 네 자료를 현재 full-load batch source child에 바로 추가하지 않는다. 대신 후보별 후속 작업으로 분리한다.

1. `도로명주소 출입구 정보`는 T-039 후보로 둔다. SHP가 아니라 direct `bd_mgt_sn + EPSG:5179 point` 텍스트라 현재 `tl_locsum_entrc` 후해소 실패와 C4 이상치 분석에 가장 직접적인 보완 후보다.
2. `도로명주소 건물 도형`은 T-040 후보로 둔다. `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC` bundle이며 전자지도 `TL_SPBD_BULD` 단순 중복이 아니다.
3. `건물군 내 상세주소 동 도형`은 T-041 후보로 둔다. 상세주소 동 polygon/point는 주소 대표 좌표보다 세밀하므로 serving path가 아니라 디버그 UI/상세주소 기능 요구가 있을 때 붙인다.
4. `구역의 도형`은 현재 전자지도 행정구역/기초구역과 중복되는 레이어가 많고, `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA`만 추가 가치가 있다. 관리 UI 또는 품질 분석 필요가 생길 때 T-041 범위에서 검토한다.
5. 후속 loader는 모두 `source_yyyymm` 기준월을 명시하고, 현재 full-load 기준월과 섞는 경우 C10 또는 별도 consistency note로 드러내야 한다.

### 근거

- 기준월이 다르다. 세종 샘플의 별도 도형/출입구 자료는 `202605` 계열이고, 현재 full-load 기준은 도로명주소 한글 `202603`, 위치정보요약/내비 `202604`, 전자지도 `202604`다.
- `mv_geocode_target`은 `bd_mgt_sn` unique와 대표 좌표를 전제로 한다. 상세주소 동이나 다중 출입구를 즉시 펼치면 API cardinality와 MV unique index 계약이 깨질 수 있다.
- `도로명주소 출입구 정보`는 보완 가치가 크지만 기존 `locsum`, `navi`, `TL_SPBD_ENTRC`와 우선순위/중복 제거 규칙을 정해야 한다.
- `구역의 도형`은 이미 적재 중인 행정구역 계열과 많이 겹치므로, 지금 추가하면 load time과 스키마만 늘고 serving 개선은 불명확하다.

### 결과

- T-030은 문서와 실제 파일 구조 테스트만 남긴다.
- T-039/T-040/T-041을 새 backlog로 추가한다.
- T-027 최종 클린 적재 전까지 이 자료들은 "누락"이 아니라 "검토 후 분리된 후속 후보"로 취급한다.

### 남은 위험

- `도로명주소 출입구 정보`가 실제로 C4 이상치를 얼마나 줄이는지는 DB 적재 비교 전까지 모른다.
- `도로명주소 건물 도형`과 전자지도 `TL_SPBD_BULD`의 관계는 row count만으로 충분하지 않다. geometry overlap, `ADR_MNG_NO`/natural key 매칭률, 기준월 차이를 T-040에서 비교해야 한다.

---

## ADR-024: `도로명주소 출입구 정보`는 별도 테이블에 저장하고 same-month direct fallback으로 사용한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-039 구현

### 컨텍스트

T-030에서 `도로명주소 출입구 정보` ZIP이 SHP가 아니라 `RNENTDATA_2605_<시군구코드>.txt` 텍스트이며, 각 row가 direct `bd_mgt_sn`과 EPSG:5179 좌표를 제공함을 확인했다.

기존 `tl_locsum_entrc`는 위치정보요약DB 기반 출입구 좌표 정본이지만 실제 `entrc_*.txt`에 `bd_mgt_sn`이 없어 후처리 해소가 필요하다. 전국 full-load 기준으로 이 해소 실패가 C3 WARN의 큰 원인이었고, C4 일부 이상치는 locsum 좌표와 polygon 사이의 거리 문제를 드러냈다.

T-039에서 실제 17개 ZIP을 읽어 계측한 결과:

- 총 원천 행 수는 6,418,169행이다.
- 모든 row는 19컬럼이며 `ent_source_cd='RM'`, `ent_detail_cd='01'`이다.
- 세종과 경남 샘플에서 `bd_mgt_sn`은 행마다 유일했다.
- 반면 `ent_man_no`는 일부 row에서 비어 있었다. 세종 9건, 경남 100건이 빈 값이었다.
- 세종 원천 27,868행 중 유효 좌표 적재 대상은 27,779행이었다.

### 결정

`도로명주소 출입구 정보`를 기존 `tl_locsum_entrc`에 섞어 넣지 않고, 별도 테이블 `tl_roadaddr_entrc`에 적재한다.

핵심 규칙:

1. `tl_roadaddr_entrc`의 PK는 `bd_mgt_sn` 단독으로 둔다.
2. `ent_man_no`는 nullable 원천 보존 필드로 둔다.
3. 좌표가 비어 있거나 `0/0` sentinel인 row는 `geom NOT NULL` 테이블에 적재하지 않는다.
4. `mv_geocode_target` 대표 좌표는 `tl_locsum_entrc` → same-month `tl_roadaddr_entrc` → `tl_navi_buld_centroid` 순서로 선택한다. same-month는 `tl_roadaddr_entrc.source_yyyymm`이 현재 `tl_juso_text.source_yyyymm` 집합에 포함되는 경우다.
5. direct entrance와 locsum entrance 모두 API 응답의 기존 `pt_source='entrance'` 계약을 유지한다.
6. `roadaddr_entrance_load`는 API/CLI job으로 제공하지만 기본 `full_load_batch` child에는 넣지 않는다.
7. C3/C4/C6/C7/C8은 `tl_locsum_entrc`와 same-month `tl_roadaddr_entrc`를 합친 대표 출입구 CTE를 사용한다.
8. C10은 `tl_roadaddr_entrc.source_yyyymm`을 기준월 비교 대상에 포함한다. T-027 최종 클린 적재 보강 이후 C10은 row-level `source_yyyymm` 집계를 우선하고 `load_manifest`를 fallback으로 사용한다.

### 근거

- direct `bd_mgt_sn`은 후해소 실패를 피하므로 serving 대표 좌표 후보로 가치가 높다.
- 기존 `tl_locsum_entrc`에 임의 삽입하면 원천 의미가 섞인다. locsum은 `sig_cd + ent_man_no` PK와 `ent_se_cd` 대표/부속 구분을 갖지만, RNENTDATA는 건물당 대표 출입구 1건 형태에 가깝고 `ent_man_no`도 nullable이다.
- 새 `pt_source` 값을 추가하면 vworld 호환 응답과 기존 클라이언트 처리에 영향을 준다. 지금은 `entrance`라는 큰 분류를 유지하고, 세부 원천은 운영 테이블과 정합성 sample에서 본다.
- 기준월이 202605 계열이라 기본 full-load에 자동 포함하면 C10 경고가 상시 발생할 수 있다. T-027 실제 재검증에서는 기준월이 다른 direct 출입구를 serving 좌표로 우선 사용했을 때 C4/C6/C7 오류도 증가했다. 따라서 운영자가 명시적으로 적재하더라도 같은 기준월 세트일 때만 MV serving 후보로 반영한다.

### 결과

- T-039에서 DDL/Alembic `0005_t039_roadaddr_entrance_table`, loader, CLI `load roadaddr-entrances`, API job kind `roadaddr_entrance_load`를 추가했다.
- `mv_geocode_target`은 `tl_roadaddr_entrc`가 비어 있거나 기준월이 다르면 기존 locsum/navi 동작과 동일하다.
- 같은 기준월의 `tl_roadaddr_entrc`를 적재한 뒤 `refresh mv --swap`을 실행하면 direct entrance가 locsum 결측 건의 fallback 대표 좌표가 될 수 있다.

### 남은 위험

- T-027 최종 클린 적재에서는 `RNENTDATA_2605_*`를 함께 적재하되 same-month gate를 적용해 serving 승격을 보류했다. 남은 위험은 같은 기준월 세트에서 direct fallback이 실제로 C3를 줄이면서 C4/C6/C7을 악화시키지 않는지 재측정하는 것이다.
- `RNENTDATA_2605_*`와 다른 기준월의 `rnaddrkor_*`, `locsum`, SHP를 섞는 운영 모드에서는 C10 WARN을 정상적인 운영 경고로 해석하되, direct 출입구는 분석용으로만 둔다.
- direct entrance와 locsum entrance의 좌표 차이가 큰 건에 대해 어느 원천을 신뢰할지, 데이터 품질 대시보드에서 비교 sample을 추가할 필요가 있다.

---

## ADR-025: `도로명주소 건물 도형` bundle은 전자지도 테이블에 섞지 않고 별도 분석 후보로 둔다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-040 구현

### 컨텍스트

T-030에서 `도로명주소 건물 도형` ZIP이 `TL_SGCO_RNADR_MST` polygon, `TL_SPBD_ENTRC` point, `TL_SPOT_CNTC` polyline으로 구성된 address building bundle임을 확인했다. 이름은 기존 도로명주소 전자지도 `TL_SPBD_BULD`/`TL_SPBD_ENTRC`와 비슷하지만 row count가 달라 단순 중복인지, 보완 원천인지 확인이 필요했다.

T-040에서 세종특별자치시와 경상남도 실제 파일을 비교했다. address polygon key는 `SIG_CD + RN_CD + BULD_SE_CD + BULD_MNNM + BULD_SLNO + BUL_MAN_NO + EQB_MAN_SN`으로, 출입구 key는 `SIG_CD + BUL_MAN_NO + ENT_MAN_NO + EQB_MAN_SN`으로 비교했다.

주요 결과:

| 지역 | bundle `TL_SGCO_RNADR_MST` | 전자지도 `TL_SPBD_BULD` | 교집합 | bundle only | 전자지도 only |
|------|---------------------------:|-------------------------:|-------:|------------:|--------------:|
| 세종 | 27,792 | 55,819 | 15,339 | 12,453 | 40,480 |
| 경남 | 656,230 | 1,269,029 | 345,290 | 310,940 | 923,739 |

출입구 point는 대부분 겹치지만 완전히 같지 않았다. 세종은 bundle only 345건, 전자지도 only 21건이고, 경남은 bundle only 5,302건, 전자지도 only 19건이다.

### 결정

`도로명주소 건물 도형` bundle을 현행 `tl_spbd_buld_polygon` 또는 `tl_locsum_entrc`에 섞지 않는다. T-040에서는 비교 helper와 문서만 추가하고 serving loader는 만들지 않는다.

후속 loader가 필요하면 다음처럼 별도 테이블을 만든다.

| 후보 테이블 | 원천 layer | 역할 |
|-------------|------------|------|
| `tl_roadaddr_buld_polygon` | `TL_SGCO_RNADR_MST` | 주소 단위 polygon 품질 분석과 debug overlay |
| `tl_roadaddr_buld_entrc` | `TL_SPBD_ENTRC` | bundle 출입구와 T-039 direct 출입구/전자지도 출입구 차이 분석 |
| `tl_roadaddr_spot_cntc` | `TL_SPOT_CNTC` | C8 도로 인접성/connection line 분석 |

### 근거

- address bundle polygon과 전자지도 building polygon의 natural key 교집합이 낮아, 기존 테이블에 덮어쓰면 C1/C2 의미가 바뀐다.
- T-039 direct 출입구 텍스트가 이미 `bd_mgt_sn + 5179 point`를 제공하므로 대표 좌표 보강은 이 SHP bundle보다 단순한 경로가 있다.
- bundle 기준월이 `202605`라 기본 `202603~202604` full-load에 자동 포함하면 C10 경고가 의도적으로 발생한다.
- `TL_SPOT_CNTC` connection line은 C8 분석에 가치가 있지만, `mv_geocode_target`의 1주소 1행 serving 계약과는 별개다.

### 결과

- `src/kraddr/geo/loaders/building_shape_bundle.py`와 `scripts/compare_building_shape_bundle.py`를 추가해 실제 DBF key overlap을 재현 가능하게 했다.
- 빠른 세종 실제 파일 테스트는 기본 pytest에 포함하고, 경남 full key scan은 `KRADDR_GEO_SLOW_REAL_DATA=1` 선택 테스트로 둔다.
- T-041에서 상세주소 동/구역 추가 레이어도 검토 완료했다. 두 원천 모두 기본 full-load/MV에는 섞지 않고 별도 overlay/분석 후보로 둔다.

---

## ADR-026: 상세주소 동 도형과 구역 추가 레이어는 serving MV가 아니라 별도 overlay/분석 후보로 둔다

- 상태: accepted, partially amended by ADR-027
- 날짜: 2026-05-26
- 결정자: codex, T-041 구현

### 컨텍스트

T-030에서 `건물군 내 상세주소 동 도형`과 `구역의 도형` ZIP이 현재 full-load 기본 경로에 들어가지 않는 별도 원천으로 식별됐다. T-039/T-040에서 direct 출입구와 도로명주소 건물 도형 bundle을 먼저 처리한 뒤, T-041에서 남은 두 원천을 세종특별자치시와 경상남도 실제 파일로 다시 비교했다.

`건물군 내 상세주소 동 도형`은 다음 두 레이어를 갖는다.

- `TL_SGCO_RNADR_DONG`: 상세주소 동 polygon
- `TL_SPBD_ENTRC_DONG`: 상세주소 동 출입구 point

`구역의 도형`은 전자지도와 이름이 같은 5개 레이어와 추가 2개 레이어를 갖는다.

- 기존 전자지도 중복 후보: `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`
- 추가 후보: `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA`

### 실제 비교 결과

상세주소 동 polygon은 전자지도 `TL_SPBD_BULD`의 부분집합이었다. 비교 key는 `BD_MGT_SN + EQB_MAN_SN`이다.

| 지역 | 상세주소 동 polygon | 전자지도 `TL_SPBD_BULD` | 교집합 | 상세주소 동 only | 전자지도 only |
|------|--------------------:|-------------------------:|-------:|-----------------:|--------------:|
| 세종 | 40,478 | 55,819 | 40,478 | 0 | 15,341 |
| 경남 | 923,702 | 1,269,029 | 923,702 | 0 | 345,327 |

상세주소 동 출입구는 모든 상세주소 동 polygon에 제공되지 않았다. `SIG_CD + BUL_MAN_NO` 기준으로 세종은 4,098행이 2,182개 building ref를, 경남은 35,649행이 16,260개 building ref를 가리켰다.

`구역의 도형`의 중복 후보 5개 레이어는 세종/경남에서 전자지도와 key 기준 완전히 같았다.

| 지역 | 중복 레이어 | 결과 |
|------|-------------|------|
| 세종 | `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS` | 모든 key 교집합 100%, 좌우 only 0 |
| 경남 | `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS` | 모든 key 교집합 100%, 좌우 only 0 |

추가 레이어는 별도 의미를 갖는다.

- `TL_SCCO_GEMD.EMD_CD`는 같은 ZIP의 `TL_SCCO_EMD.EMD_CD`와 교집합이 0건이었다. 기존 읍면동 테이블에 union하면 코드 의미가 섞일 수 있다.
- `TL_SPPN_MAKAREA`는 `SIG_CD + MAKAREA_ID`가 distinct key다. 세종 146행, 경남 3,486행 모두 distinct였다.

### 결정

두 원천 모두 현행 `mv_geocode_target`과 기본 `full_load_batch`에 자동 포함하지 않는다.

1. `건물군 내 상세주소 동 도형`은 기존 `tl_spbd_buld_polygon`에 섞지 않는다. 필요하면 `tl_detail_dong_polygon`, `tl_detail_dong_entrc` 같은 별도 overlay 테이블을 둔다.
2. `구역의 도형`의 중복 5개 레이어는 다시 적재하지 않는다.
3. `TL_SCCO_GEMD`와 `TL_SPPN_MAKAREA`는 필요하면 각각 `tl_scco_gemd`, `tl_sppn_makarea` 같은 별도 테이블로 적재한다.
4. 이 레이어들은 serving 대표 좌표를 바꾸는 원천이 아니라 디버그 UI overlay, 상세주소 기능, 품질 분석용 원천으로 취급한다.
5. 기준월이 `202605` 계열이므로 기존 `202603~202604` full-load와 섞을 때는 C10 경고 또는 별도 consistency note로 드러낸다.

ADR-027은 이 결정 중 `TL_SPPN_MAKAREA`의 용도를 보강한다. `TL_SPPN_MAKAREA`는 여전히 `mv_geocode_target`에는 union하지 않지만, 단순 overlay보다 높은 가치가 있는 국가지점번호 표기 의무지역 polygon이므로 별도 테이블로 적재해 geocode/reverse geocode 보조 데이터로 활용한다.

### 근거

- `mv_geocode_target`은 1주소 1행과 대표 좌표를 전제로 한다. 상세주소 동 polygon/출입구를 즉시 펼치면 결과 cardinality와 응답 계약이 바뀐다.
- 상세주소 동 polygon은 전자지도 building polygon의 부분집합이므로, 기본 건물 polygon 검증을 대체하면 전체 건물이 아니라 상세주소 동 대상 건물만 검증하게 된다.
- 구역 중복 레이어 5개는 전자지도에 이미 있으므로 다시 적재해도 serving 개선이 없다.
- `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key가 겹치지 않아 같은 테이블에 합치면 침묵하는 의미 충돌이 생길 수 있다.

### 결과

- `src/kraddr/geo/loaders/shape_dbf.py`를 추가해 DBF/SHP key-set 분석 helper를 공용화했다.
- T-040의 `building_shape_bundle.py`는 이 공용 helper를 사용하도록 정리했다.
- `src/kraddr/geo/loaders/extra_shape_layers.py`와 `scripts/compare_extra_shape_layers.py`를 추가했다.
- 빠른 세종 실제 파일 테스트는 기본 pytest에 포함하고, 경남 full key scan은 `KRADDR_GEO_SLOW_REAL_DATA=1` 선택 테스트로 둔다.

### 남은 위험

- `TL_SCCO_GEMD`의 정확한 업무 의미는 제공자 PDF/레이아웃 문서 해석이 더 필요하다. 이번 결정은 key overlap과 현행 serving 계약 기준의 보류 결정이다.
- `TL_SPPN_MAKAREA`는 ADR-027에서 국가지점번호 보조 데이터로 용도를 확정했지만, 개별 국가지점번호판 point 목록이 아니라 표기 의무지역 polygon이라는 한계를 갖는다. 국가지점번호 문자열 parser/generator는 별도 설계가 필요하다.
- 상세주소 동 도형을 사용자 기능으로 노출하려면 주소 검색 결과에서 동/호/출입구를 어떻게 랭킹하고 응답할지 별도 DTO/API 설계가 필요하다.

---

## ADR-027: `TL_SPPN_MAKAREA`는 국가지점번호 보조 지오코딩 데이터로 별도 적재한다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-26
- 결정자: codex, 사용자 T-041 보강 지시

### 컨텍스트

ADR-026은 `구역의 도형` ZIP에서 추가 가치가 있는 레이어로 `TL_SCCO_GEMD`와 `TL_SPPN_MAKAREA`를 식별했지만, 둘 다 기본 serving path에는 넣지 않고 overlay/분석 후보로 보류했다. 이후 `TL_SPPN_MAKAREA`의 의미를 다시 확인했다.

`TL_SPPN_MAKAREA`는 "지점번호표기 의무지역" polygon으로 해석한다.

| 이름 부분 | 의미 |
|-----------|------|
| `TL` | Table 또는 Layer |
| `SPPN` | Spot Point Position Number, 국가지점번호/지점번호 계열 |
| `MAKAREA` | Marking Area, 표기 의무 구역 |

행정안전부 설명자료는 국가지점번호 제도를 산악·해안 등 건물이 없는 비거주지역에서 사고·재난 발생 시 정확한 위치 안내를 돕기 위한 제도로 설명한다. 같은 설명자료는 표기 대상 지역을 도로명이 부여된 도로에서 100m 이상 떨어진 지역 중 시·도지사가 필요하다고 고시한 지역으로 설명하고, 표기 대상 시설물을 지면 또는 수면에서 50cm 이상 노출된 고정 시설물로 설명한다.

따라서 `TL_SPPN_MAKAREA`는 주소가 없거나 주소 후보 confidence가 낮은 비거주지역에서 geocode/reverse geocode를 보조할 수 있다. 다만 이 레이어는 개별 국가지점번호판이나 시설물 point 목록이 아니라 의무지역의 경계 polygon이다.

### 결정

`TL_SPPN_MAKAREA`를 별도 테이블 `tl_sppn_makarea`로 적재한다. T-042에서 DDL, loader, 국가지점번호 parser/formatter, geocode/reverse 보조 조회, source set optional child를 1차 구현했다.

1. `mv_geocode_target`에는 union하지 않는다. 이 MV는 도로명/지번 주소 1행 계약을 유지한다.
2. reverse geocode는 입력 좌표가 `tl_sppn_makarea.geom`에 포함될 때 국가지점번호 표기 의무지역 metadata를 보조 후보로 반환할 수 있다.
3. geocode는 국가지점번호 문자열 parser가 좌표를 계산한 뒤, 그 좌표가 `tl_sppn_makarea` 안에 있는지 검증하고 `MAKAREA_NM` 등 구역 문맥을 붙인다. EPSG:5179 좌표에서 국가지점번호 문자열을 만드는 formatter는 실제 polygon 내부 점 기반 테스트와 UI 표시를 지원한다.
4. `MAKAREA_NM`만으로 정확한 geocode 좌표를 만들지는 않는다. 구역명 검색은 polygon centroid/bbox를 낮은 confidence로 반환하는 별도 `search` 또는 관리 UI overlay 기능으로 분리한다.
5. 응답 확장은 vworld 호환 필드를 오염시키지 않고 `x_extension.sppn_makarea`로 둔다. reverse geocode 결과의 도로명/지번 후보는 기존 `result`에 유지하고, 표기 의무지역 polygon 문맥은 보조 확장 배열에 담는다.
6. 후속 loader는 `SIG_CD + MAKAREA_ID`를 primary key로 사용하고, `source_file`, `source_yyyymm`, `loaded_at`을 남긴다.

### 제안 테이블

```sql
CREATE TABLE tl_sppn_makarea (
  sig_cd        TEXT NOT NULL,
  makarea_id    TEXT NOT NULL,
  ntfc_yn       TEXT,
  makarea_nm    TEXT,
  ntfc_de       TEXT,
  mvm_res_cd    TEXT,
  mvmn_resn     TEXT,
  opert_de      TEXT,
  makarea_ar    NUMERIC(12,3),
  mvmn_desc     TEXT,
  geom          geometry(MultiPolygon, 5179) NOT NULL,
  source_file   TEXT NOT NULL,
  source_yyyymm TEXT,
  loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, makarea_id)
);

CREATE INDEX idx_sppn_makarea_geom
  ON tl_sppn_makarea
  USING GIST (geom);
```

원천 SHP는 T-041 세종/경남 측정 기준 `Polygon`으로 제공된다. 운영 테이블은 다른 polygon 계열과 같은 방식으로 `MultiPolygon`으로 통일하고, loader에서 `ST_Multi()` 또는 GDAL `PROMOTE_TO_MULTI`로 변환한다.

### 쿼리 원칙

reverse geocode는 입력 좌표를 한 번만 EPSG:5179로 변환하고, polygon 컬럼에는 함수를 씌우지 않는다.

```sql
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179) AS geom
)
SELECT m.sig_cd, m.makarea_id, m.makarea_nm
FROM tl_sppn_makarea m, target_pt p
WHERE ST_Covers(m.geom, p.geom)
ORDER BY ST_Area(m.geom) ASC
LIMIT 5;
```

`ST_Contains` 대신 `ST_Covers`를 사용해 경계 위 좌표도 포함한다. 여러 구역이 겹치면 작은 면적을 우선하고, 필요하면 행정구역 코드(`SIG_CD`)와 거리/면적 metric을 함께 반환한다.

### 결과

- T-041 문서와 데이터 모델 문서에서 `TL_SPPN_MAKAREA`를 단순 overlay 후보가 아니라 국가지점번호 보조 geocode/reverse 데이터 후보로 승격한다.
- T-042에서 `tl_sppn_makarea` DDL/Alembic, loader, CLI/API job kind, source set optional child, `SppnMakareaContext`, 국가지점번호 parser/formatter, geocode/reverse `x_extension.sppn_makarea`를 구현했다.
- Docker PostGIS `kraddr_geo_t042_sppn`에서 세종 `구역의 도형` 실제 ZIP을 적재해 146행/146 distinct key/전체 valid MultiPolygon을 확인했다.
- `금이산` polygon 내부 점을 EPSG:5179 formatter로 `다바 7363 4856`으로 만든 뒤 geocode와 reverse 보조 조회가 같은 polygon 문맥을 반환하는 것을 확인했다.
- T-027 최종 클린 로드는 `sppn_makarea` optional source를 포함할 수 있다. 다만 원천 기준월이 다른 경우 ADR-029/T-045의 혼합 기준월 확인 UX를 그대로 따른다.

### 남은 위험

- `TL_SPPN_MAKAREA`는 개별 국가지점번호판 point 목록이 아니므로, polygon 포함 여부는 "해당 좌표가 표기 의무지역 안에 있다"는 문맥만 제공한다. 실제 시설물 point 원천을 확보하면 별도 source와 confidence 정책을 둔다.
- reverse geocode는 도로명/지번 후보 유무와 관계없이 `sppn_makarea` 보조 조회를 수행한다. 응답 크기와 latency가 문제되면 T-047에서 후보 confidence 또는 radius 정책으로 제한한다.
- 국가지점번호 parser/formatter는 공개 설명의 100km 한글 격자와 10m cell 규칙을 구현했다. 도로명주소 전자지도 PDF 사양서에 더 엄격한 표기 변형이 있으면 T-047/T-044 전에 parser 허용 범위를 재검토한다.
- 디버그 UI polygon overlay는 아직 구현하지 않았다. T-044에서 최신 `maplibre-vworld-js` wrapper로 추가한다.

### 참고

- 행정안전부 설명자료: `https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000009&nttId=66987`

---

## ADR-035: `python-kraddr-base`의 Address 조합/분리 코드를 흡수하고 외부 라이브러리 의존성을 끊는다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude

### 컨텍스트

같은 WSL ext4 환경의 `~/dev/python-kraddr-base`는 한국 주소 도메인 공통 helper(주소 조합/분리, 정규화, 외부 API client 등)를 제공해 왔다. 사용자 RFC에 따라 `python-kraddr-base` 라이브러리는 archive 예정이다. 본 저장소 `python-kraddr-geo`는 이 라이브러리에 명시·암시적으로 의존하는 표면이 있을 수 있으므로, 필요한 부분만 흡수해 외부 dependency를 제거해야 한다.

### 결정

`python-kraddr-base` 중 **주소 문자열의 조합(compose)과 분리(parse) 코드만** 본 저장소로 흡수한다.

- 흡수 대상: `kraddr.base.address.parser`, `kraddr.base.address.composer`, `kraddr.base.address.types`, `kraddr.base.address.normalize` (실제 모듈명/경로는 인벤토리 단계에서 확정).
- 흡수 위치: `src/kraddr/geo/core/address/{parser,composer,types,normalize}.py`. 기존 `core/normalize.py`는 thin shim으로 유지해 하위 호환 보장.
- 흡수 파일 최상단에 origin(원본 commit SHA + 원본 경로) 주석을 추가한다.
- 단위 테스트와 fixtures도 함께 이관(`tests/unit/core/test_address_*.py`).
- 흡수 대상이 아닌 모듈(외부 API client, I/O helper 등)은 가져오지 않는다.
- 본 저장소의 `pyproject.toml`/`requirements*.txt`에서 `kraddr-base` dependency를 제거하고, 모든 `from kraddr.base.*` import를 `from kraddr.geo.core.address.*`로 교체한다.

### 근거

- `python-kraddr-base`는 곧 archive되므로, 본 저장소가 의존하면 빌드/CI/배포 위험이 발생한다.
- Address 조합/분리는 본 저장소의 PNU generated column 규칙(ADR-010)과 직접 맞물려 있어 같은 저장소에서 관리하는 것이 정합성에 좋다.
- 라이브러리 분리를 유지하기에는 본 저장소가 유일한 consumer일 가능성이 높다.

### 결과

- T-056에서 흡수 PR을 작성한다.
- 흡수 완료 후 `python-kraddr-base`는 read-only archive로 전환하고, journal에 archive URL과 마지막 commit SHA를 남긴다.
- 흡수 전후 응답 차이가 없는지 fixture 기반 회귀 테스트로 확인한다.

### 남은 위험

- 흡수 대상 모듈이 다른 외부 라이브러리에 의존한다면 단순 흡수가 어려울 수 있다. 발견 시 미흡수 결정 또는 본 저장소에서 재작성.
- 라이선스가 호환되지 않으면 코드 그대로 가져오지 않고 본 저장소에서 동일 의미의 helper를 처음부터 작성한다.
- archive 시점 이후 외부에서 fix가 들어오면 본 저장소는 자동 반영하지 않는다. cherry-pick 또는 별도 PR로 처리.

---

## ADR-036: 적재 완료 DB Restore는 같은 cluster 안 `ALTER DATABASE RENAME` 기반 hot-swap을 1차 패턴으로 지원한다

- 상태: accepted (문서 설계, 구현 전, ADR-030 결과 섹션 amend)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude

### 컨텍스트

ADR-030 / T-046은 적재 완료 DB의 backup/restore 워크플로를 정의했지만, 복원은 "기본 새 빈 DB"만 명문화하고 운영 serving DB로의 즉시 전환(hot-swap)은 "별도 위험 경로"로만 언급했다. 운영 시나리오:

1. T-046으로 복원본 DB(`kraddr_geo_restore_<ts>`)를 만든다.
2. smoke/consistency/performance gate가 통과한다.
3. 운영 serving DB(`kraddr_geo`)를 복원본으로 즉시 교체한다.

이를 위한 결정과 절차를 명문화한다.

### 결정

복원본 DB가 운영 serving DB와 **같은 PostgreSQL cluster 안**에 있는 경우, `ALTER DATABASE ... RENAME TO ...` 기반 hot-swap을 1차 패턴으로 지원한다.

1. 사전 조건: `ops.maintenance_windows(kind='restore', state='active')` + typed confirmation hash 일치 + 복원본 DB smoke/consistency 통과.
2. swap 절차:
   - maintenance용 별도 DB(`postgres` 또는 admin DB) connection 사용.
   - 두 DB의 기존 connection을 `pg_terminate_backend`로 종료.
   - 운영 DB → `<current>_previous_<ts>` 로 rename.
   - 복원본 DB → `<current>` 로 rename.
   - application engine pool refresh.
   - post-swap smoke test 실행.
3. release/audit 연계:
   - 새 `ops.serving_releases(release_kind='restore', previous_release_id=...)` row 생성.
   - `ops.audit_events`에 `serving_release.hot_swap.started|succeeded|failed|rolled_back` 4종 outcome 기록.
4. rollback 절차: `<current>_previous_<ts>` alias가 retention 기간 안이면 같은 절차로 반대 방향 rename. 새 `release_kind='rollback'` row 생성, `rollback_target_release_id`로 원본 release 참조.
5. 다른 host/cluster로의 fail-over(cluster 간 hot-swap)는 본 ADR 범위가 아니다. 별도 ADR/task에서 다룬다.

### 근거

- `ALTER DATABASE ... RENAME`은 metadata-only ALTER로 < 1초 안에 완료. application DSN을 바꾸지 않고 같은 cluster 안에서 즉시 교체 가능.
- ADR-033의 `ops.serving_releases` + `ops.maintenance_windows` + active partial unique index가 동시 swap을 DB 수준에서 1건으로 제한한다.
- application 변경 범위는 engine pool refresh + maintenance connection helper로 한정된다. application 코드 침투 최소.
- DSN switch 방식(다른 host fail-over)은 본 task scope를 넘는다. 별도 ADR/task.

### 결과

- T-058에서 hot-swap 구현 PR을 작성한다.
- ADR-030 "결과/후속" 섹션에 본 결정을 참조하는 amend를 추가한다.
- REST: `POST /v1/admin/restores/{job_id}/hot-swap`, `POST /v1/admin/serving-releases/{release_id}/rollback`.
- CLI: `kraddr-geo serving hot-swap`, `kraddr-geo serving rollback`.
- 통합 검증은 대구광역시 부분 DB로 backup → restore → hot-swap → smoke → rollback round-trip.

### 남은 위험

- swap 중 `pg_terminate_backend`로 모든 connection을 끊으므로 in-flight query 중단이 호출자에게 노출된다. LB drain + 호출자 retry로 보완.
- multi-process(Gunicorn workers) 환경은 worker별 engine refresh 신호 필요.
- `<current>_previous_<ts>` alias retention 종료 후에는 rollback 불가. retention 기간(권장 7일)을 운영자가 설정.
- 복원본 DB가 다른 PostgreSQL major version에서 만들어졌다면 hot-swap 거절(major mismatch hard-fail).

---

## ADR-037: 외부 IP에서 호출되는 REST API는 대한민국 IP만 허용한다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude

### 컨텍스트

본 라이브러리는 행안부 도로명주소·우편번호·내비DB·전자지도 자료와 vworld/kakao/naver fallback을 사용한다. 모두 한국 사용 전제로 약관이 작성되어 있고, 외부 fallback의 호출 한도도 한국 IP 기준이다. REST API 표면을 한국 외 공용 IP에 그대로 노출하면 약관·호출 한도·법적 책임 모두 문제가 된다. ADR-013은 디버그/관리 UI를 사내 내부망 전용으로 두었지만, 일반 `/v1/*` 엔드포인트의 외부 노출 정책은 명문화되지 않았다.

### 결정

REST API 표면은 **외부(공용) IP에서 호출될 때 대한민국 IP만 허용**한다.

1. 적용 대상: `/v1/geocode`, `/v1/reverse`, `/v1/search`, `/v1/zipcode`, `/v1/pobox`, `/v1/admin/*`, `/v2/*`(T-052 신규).
2. 적용 제외: `/healthz`, `/metrics`(uptime/probe 호환).
3. 내부 사설/loopback IP는 그대로 허용(`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1/128`, `fc00::/7`, `fe80::/10`).
4. 외부 공용 IP는 GeoIP DB(MaxMind GeoLite2 Country 등) 조회로 country code `KR`만 허용.
5. `Settings.geoip_allow_cidrs`/`geoip_deny_cidrs`로 명시 override 가능. 우선순위: `deny > allow > 사설/loopback > KR > 기본 deny`.
6. 구현 위치: FastAPI middleware(`api/middleware/geoip_gate.py`). nginx/reverse proxy layer는 추가 layer로 운영 가능하지만 기본 안전망은 application에서 보장.
7. deny 발생 시 HTTP 403 + 한국어/영어 분리 메시지 + `ops.audit_events(action='geoip.denied', payload_redacted={client_country, path, ...})` 기록. IP는 hash로만 저장(ADR-033).
8. GeoIP DB 부재 시 `geoip_gate_mode`로 동작 선택:
   - `strict`(기본): 외부 IP 전부 deny.
   - `permissive`: 모두 allow + log warning(개발 환경).
   - `off`: gate 비활성화(테스트 전용).
9. `X-Forwarded-For` 처리: `Settings.geoip_trusted_proxies`에 명시된 hop만큼 pop해 실제 client IP 추출. trust 안 된 proxy 뒤의 값은 무시.

### 근거

- 외부 데이터 약관(도로명주소, 우편번호, vworld 등)과 호출 한도가 한국 IP 기준이다. 한국 외 호출은 약관 위반 위험.
- ADR-013은 디버그/관리 UI만 다뤘다. 일반 REST 표면의 외부 노출은 별도 결정 필요.
- 라이브러리 사용자가 `uvicorn kraddr.geo.api.app:app`만 실행해도 외부 차단이 작동해야 한다. application layer 보호가 1차 안전망.
- 사설/loopback 허용으로 사내망/Docker 네트워크는 영향 없음.

### 결과

- T-054에서 middleware + GeoIpSettings + audit 연계를 구현한다.
- `kraddr-geo geoip check <ip>` CLI 진단 helper 추가.
- 운영자는 월 1회 MaxMind license key로 GeoIP DB 갱신.
- `/admin/stats`(T-053)에 KR vs non-KR 요청 분포 시각화.

### 남은 위험

- GeoIP DB는 IP-country 매핑이 100% 정확하지 않다. mobile/CDN IP 갱신 lag.
- `X-Forwarded-For` spoofing — `trusted_proxies` 미설정 시 잘못된 client IP 신뢰.
- 한국 사용자가 외부 VPN/proxy를 통해 접근하면 차단 가능. 운영 공지 필요.
- 본 gate는 application layer다. nginx/firewall layer 차단이 더 빠르고 안전하므로, 본 라이브러리는 "기본 안전망" 위치.

---

## ADR-038: API 표면을 v1(vworld 호환)과 v2(외부 provider 흡수 + 통합 candidate)로 분리하고 AI-friendly 문서를 둔다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude

### 컨텍스트

본 라이브러리는 vworld OpenAPI 응답 형식 호환을 핵심 정체성으로 둔다(ADR-007/-012). 그러나 운영 현장에서는 kakao Local API와 naver Geocoding/Reverse API 패턴(키워드 검색, 카테고리, 도로명/지번 동시 응답, region polygon 정보 등)도 활용 가치가 있다. 한 응답 schema에 vworld + kakao + naver를 모두 욱여넣으면 vworld 호환이 깨지고, 분리하지 않으면 새 기능을 받기 어렵다.

### 결정

API 표면을 **v1**(기존 호환)과 **v2**(신규)로 분리한다.

1. **v1**: `/v1/*` 경로 + 현재 DTO 그대로 동결. vworld 호환 key 명명(`addresses[]`, `result.point`, `x_extension.*`) 유지.
2. **v2**: `/v2/geocode`, `/v2/reverse`, `/v2/search`, `/v2/region/lookup`, `/v2/zipcode/{zip_no}`, (선택) `/v2/transform`. 자체 candidate-list schema, `confidence`/`match_kind`/`source` 명시.
3. 라이브러리: `AsyncAddressClient`에 `geocode_v2`, `reverse_v2`, `search_v2` 함수 추가. v1 함수는 그대로.
4. 외부 provider adapter:
   - `infra/external/vworld.py`(기존): v1/v2 양쪽으로 candidate 변환.
   - `infra/external/kakao.py`(신규): kakao Local API → v2 candidate.
   - `infra/external/naver.py`(신규): naver Geocoding/Reverse → v2 candidate.
   - 외부 API key 미설정 시 adapter 사용 불가 상태로 두고 fallback은 즉시 local 응답만 반환.
5. v2 입력은 region hint(T-057 `sig_cd`/`bjd_cd`/`bbox`)를 1차 시민으로 받는다.
6. 문서화:
   - `docs/api-reference/` 디렉터리에 v1/v2/library/operators 분류로 markdown.
   - 각 endpoint별 "요약/사용 시나리오/입력 schema/출력 schema/예시(curl + Python + JSON)/에러/관련 ADR" 표준 구조.
   - `docs/api-reference/llm-summary.md`: AI agent용 전체 표면 압축 요약.
   - OpenAPI는 v1/v2 paths 모두 포함, frontend `types/api.gen.ts` 자동 갱신.
7. v1과 v2 모두 외부 호출은 `geo_cache` 캐시(ADR-009/-019).

### 근거

- vworld 호환은 기존 SDK 사용자(`kraddr-geo-ui` 포함 외부 클라이언트)에게 중요한 contract. 깨지면 안 된다.
- kakao/naver 응답 패턴을 v1에 강제 흡수하면 vworld key 명명이 흐려진다.
- 외부 provider는 fallback에서만 호출(ADR-019). 본 라이브러리의 기본 응답은 local PostGIS.
- AI agent와 사람이 동시에 읽을 수 있는 문서가 있어야 운영/디버깅이 효율적.

### 결과

- T-052에서 v2 DTO/router/adapter/문서 PR을 작성한다.
- `docs/api-reference/` skeleton + `llm-summary.md` 생성.
- v1 동결: 회귀 0 검증. `openapi.json`의 `/v1/*` paths schema diff 없음.
- kakao/naver adapter: recorded fixture 기반 단위 테스트.
- 6~12개월 후 v1 deprecation 일정은 별도 ADR.

### 남은 위험

- v1 + v2 동시 유지 비용. maintenance burden 증가.
- kakao/naver는 약관별 캐싱·재배포 제한이 다르다. cache TTL과 source 표기 정책을 ADR-019 후속에서 보강.
- v2 응답이 vworld key 명명과 분리되어, 일부 SDK 사용자가 두 schema 모두 다뤄야 한다. `docs/api-reference/v2/migration-from-v1.md` 작성으로 완화.
- 외부 provider 약관 변경 시 adapter 즉시 갱신 필요. 운영 모니터링.
