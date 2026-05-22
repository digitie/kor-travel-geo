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

- 상태: accepted
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
