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
PostgreSQL 16 + PostGIS 3.4를 1차 저장소로 채택한다. SpatiaLite 기반 구현은 `v1` 브랜치에 보존하고 master에서는 더 이상 유지보수하지 않는다.

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
| **SHP 보조** (`loaders/shp/`) | `tl_scco_ctprvn/sig/emd/li`, `tl_kodis_bas`, `tl_spbd_buld_polygon`, `tl_sprd_manage/intrvl/rw` | GDAL Python binding (ADR-005 한정 유지) | `libgdal-dev` |

`tl_spbd_buld_polygon`은 BD_MGT_SN PK만 공유하고 **속성은 모두 `tl_juso_text`에서** 채운다 — 도형과 속성의 책임을 명확히 분리.

`mv_geocode_target`은 텍스트 1차 + 출입구 좌표 + centroid fallback을 합쳐 구성한다(`docs/data-model.md`). `pt_source ∈ {entrance, navi, centroid}` 컬럼으로 응답에 좌표 출처를 노출한다.

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
2. 1단계 source load child 5종:
   - `juso_text_load`
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
- child 구성은 현재 기본 5종으로 고정되어 있다. 우편번호 대량배달처(`bulk_load`)까지 batch 필수 구성으로 넣을지는 운영 데이터셋 확보 후 조정한다.

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
