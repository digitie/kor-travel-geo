# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

## 2026-05-23 (codex, T-004 + 실제 SHP/DBF 검사)

**작업**: T-004 DTO 6종 구현 및 `data/juso/도로명주소 전자지도` 실제 파일 읽기 테스트 추가

**변경 파일**:
- 신규: `src/kraddr/geo/dto/geocode.py`, `src/kraddr/geo/dto/reverse.py`, `src/kraddr/geo/dto/search.py`, `src/kraddr/geo/dto/zipcode.py`, `src/kraddr/geo/dto/pobox.py`, `src/kraddr/geo/dto/admin.py`
- 신규: `src/kraddr/geo/loaders/juso_map.py`
- 신규: `tests/unit/test_dto_geocode.py`, `tests/unit/test_dto_reverse.py`, `tests/unit/test_dto_search_zipcode_pobox_admin.py`
- 신규: `tests/integration/test_juso_map_files.py`
- 갱신: `src/kraddr/geo/dto/__init__.py`, `pyproject.toml`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`

**결정**:
- DTO는 `docs/backend-package.md` §4의 wire contract를 우선해 pydantic v2 frozen model로 작성했다.
- `type` 필드는 vworld/API wire field이므로 DTO 파일별로 `A003` ruff ignore를 한정 적용했다.
- pydantic runtime이 nested DTO 타입을 해석해야 하므로 `GeocodeResponse`, `ReverseResultItem`, `SearchResultItem`의 address DTO imports는 runtime import로 유지하고 해당 파일에만 `TC001` ignore를 한정 적용했다.
- GDAL 적재 구현은 T-013 범위로 남긴다. 다만 이번 작업에서 순수 Python으로 SHP/DBF 헤더를 직접 열어 `강원특별자치도/51000`의 11개 마스터 레이어와 `TL_SPBD_BULD` 필드(`BD_MGT_SN`, `BULD_MNNM`, `MVM_RES_CD`, `RN_CD`, `SIG_CD` 등)를 검증했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 28 passed. 실제 파일 경로 `data/juso/도로명주소 전자지도/강원특별자치도/51000/*.shp|*.dbf|*.shx`를 열어 검사함.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**: T-005 — `infra/engine.py` async engine factory + 통합 테스트 준비.

---

## 2026-05-23 (claude, epost 데이터셋 정책)

**작업**: 우편번호 외부 API 활용 정책을 ADR-009로 확정하고 관련 문서 보강.

**변경 파일**:
- `docs/decisions.md` — ADR-009 추가 (epost 15000302, `downloadKnd=1` 분기 1회 전체 적재. 실시간 lookup 15056971 미도입).
- `docs/external-apis.md` — epost 절 보강: 데이터셋 ID 15000302, `downloadKnd` 4종 표, 분기 1회 전체 적재 흐름, 미도입 API(15056971) 명시. 한눈에 표에도 데이터셋 ID + ADR 인용.
- `docs/data-model.md` — `postal_pobox`/`postal_bulk_delivery` 위에 epost 15000302 ZIP 적재 출처와 ADR-009 인용.
- `.env.example` — `KRADDR_GEO_EPOST_API_KEY` 위 주석에 데이터셋 ID + ADR-009 표기.
- `CHANGELOG.md` — `### Added`에 ADR-009 요약.

**결정**:
- ADR-009: 우편번호 매칭은 epost 데이터셋 15000302의 전체 ZIP(`downloadKnd=1`)을 **분기 1회** 받아 `postal_pobox`/`postal_bulk_delivery`를 TRUNCATE → INSERT. 변경분 누적 미운영. 실시간 lookup API(데이터셋 15056971) 미도입.

**검증**:
- 본 실행 환경(원격 컨테이너)은 `openapi.epost.go.kr` 외부망이 차단되어 직접 호출은 못 했다. 데이터셋 ID와 `downloadKnd` 4종 정의는 공공데이터포털 검색 결과로 확정. 사용자 WSL 환경에서 키 재발급 후 `curl ... -G --data-urlencode "downloadKnd=1"`로 응답을 마지막 점검 권장.
- 사용자가 채팅에 노출한 서비스 키는 즉시 재발급(또는 활용중지) 권장. 본 PR/문서/`.env.example`에 평문 커밋 없음.

**다음**: T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 시 본 ADR을 reference로 적용. CLI에 `kraddr-geo load epost --kind=full` 같은 entry를 두고 운영은 systemd timer로 분기 트리거.

---

## 2026-05-23 (claude, GDAL 셋업 문서)

**작업**: PR #3 마무리 — GDAL 시스템 의존성을 문서로 못박는다.

**변경 파일**:
- 신규: `docs/dev-environment.md` (WSL ext4 기준 셋업, conda/Docker 대안)
- 갱신: `docs/geocoding-readiness.md` (체크리스트 0번 항목 — 시스템 GDAL 설치)
- 갱신: `docs/resume.md` ("알려진 함정"에 GDAL 버전 미스매치, `libgdal-dev` 누락)
- 갱신: `SKILL.md` §2 (빠른 시작에 `apt install libgdal-dev` + `gdal==$(gdal-config --version)` 핀 추가)
- 갱신: `pyproject.toml` (`loaders` extra 위 주석 — 시스템 의존성/Docker 권장)
- 갱신: `docs/decisions.md` (ADR-008 — 시스템 GDAL과 동일 버전 핀)

**결정**:
- ADR-008: `loaders` extra는 `pip install "gdal==$(gdal-config --version)"`로 시스템과 동일 버전 핀. 운영·CI는 `osgeo/gdal:*` Docker 베이스 표준화. ADR-005 보강.

**검증**: 문서 전용 변경이라 코드 테스트 영향 없음. T-013 진행 시 실제 GDAL 환경에서 `dev-environment.md` 절차로 재현 가능.

**다음**: T-004 (DTO 6종).

---

## 2026-05-23 (codex, 리뷰 3차 반영)

**작업**: PR 리뷰 반영 — 설정 싱글톤 helper 역할 분리

**변경 파일**:
- 갱신: `src/kraddr/geo/settings.py`, `tests/unit/test_settings.py`, `docs/backend-package.md`

**결정**:
- `reset_settings()`는 인자 없이 싱글톤을 비우는 역할만 맡는다.
- 테스트나 명시 주입이 필요할 때는 `set_settings(settings)`를 사용한다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex, 리뷰 2차 반영)

**작업**: PR 리뷰 항목 5~10 반영 — DTO 필수성, validator 범위, CLI exit, ruff ignore, 예외명, namespace package 정리

**변경 파일**:
- 갱신: `src/kraddr/geo/dto/address.py`, `src/kraddr/geo/cli/main.py`, `src/kraddr/geo/exceptions.py`, `pyproject.toml`
- 갱신: `tests/unit/test_dto_address.py`, `tests/unit/test_exceptions.py`
- 갱신: `docs/backend-package.md`, `docs/decisions.md`
- 삭제: `src/kraddr/__init__.py`

**결정**:
- `RefinedAddress.structure`는 사양대로 필수 `AddressStructure`로 둔다.
- 빈 문자열 → `None` 변환 validator는 optional address fields에만 적용하고, `level0`은 빈 문자열을 명시적으로 거부한다.
- `typer.Exit`는 인스턴스(`raise typer.Exit()`)로 raise한다.
- `N815` ruff ignore는 vworld 호환 필드가 있는 `dto/address.py`에만 한정한다.
- base 예외명은 `KraddrGeoError`로 확정한다(ADR-014).
- `kraddr` parent는 PEP 420 implicit namespace package로 둔다(ADR-015).

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex)

**작업**: PR 리뷰 반영 — 설정 기본값을 사양과 맞추고 README에 법적·데이터 사용 한계 추가

**변경 파일**:
- 갱신: `src/kraddr/geo/settings.py`, `.env.example`, `tests/unit/test_settings.py`, `README.md`

**결정**:
- `epost_download_url` 기본값은 브라우저 다운로드 페이지가 아니라 공공데이터포털 OpenAPI endpoint(`http://openapi.epost.go.kr/postal/downloadAreaCodeService/downloadAreaCodeService/getAreaCodeInfo`)로 둔다.
- `pg_statement_timeout_ms` 기본값은 사양값 5초(`5000`)로 둔다. 별도 ADR 없이 사양에 맞춘다.
- `api_default_radius_m` 기본값은 역지오코딩 hit rate를 위해 사양값 `200`으로 둔다.
- `api_cors_origins` 기본값은 빈 tuple로 둔다. localhost 허용은 `.env` override에서만 명시한다.
- README에 MIT 라이선스가 코드/문서에만 적용되고 외부 데이터/API 응답은 각 제공처 약관을 따른다는 한계를 명시했다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-22 (codex)

**작업**: T-001~T-003 구현 — Python 패키지 스캐폴드, 설정, 공통/주소 DTO와 단위 테스트 추가

**변경 파일**:
- 신규: `pyproject.toml`, `.env.example`
- 신규: `src/kraddr/__init__.py`, `src/kraddr/geo/__init__.py`, `src/kraddr/geo/version.py`, `src/kraddr/geo/py.typed`
- 신규: `src/kraddr/geo/settings.py`, `src/kraddr/geo/exceptions.py`, `src/kraddr/geo/client.py`, `src/kraddr/geo/cli/main.py`
- 신규: `src/kraddr/geo/dto/common.py`, `src/kraddr/geo/dto/address.py`
- 신규: `tests/unit/test_settings.py`, `tests/unit/test_dto_common.py`, `tests/unit/test_dto_address.py`
- 갱신: `CHANGELOG.md`, `docs/tasks.md`, `docs/resume.md`

**결정**:
- import-linter는 도구 제약상 `root_package = "kraddr"`와 `containers = ["kraddr.geo"]` 조합으로 설정한다. 이는 문서의 `kraddr.geo` 계층 계약과 같은 의미이며 실제 도구 실행이 통과하는 형태다.
- `AsyncAddressClient`와 CLI는 이번 범위에서 import/install 검증을 위한 자리표시자로만 둔다. 실제 지오코딩 기능은 T-010/T-011에서 구현한다.
- 사용자가 지정한 SHP 기준 경로 `data/juso/도로명주소 전자지도`를 확인했다. 강원도 샘플의 11개 DBF 필드는 문서의 마스터 레이어(`TL_SPBD_BULD`, `TL_SPBD_ENTRC`, `TL_SPRD_MANAGE` 등)와 맞는다.

**검증**:
- `pip install -e ".[dev]"` 통과
- `pip install -e ".[api,dev]"` 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 10 passed
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**참고**:
- 현재 작업 디렉토리가 `/mnt/f` NTFS 위라 문서의 WSL/NTFS 경고가 그대로 적용된다. 기본 `TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)를 가리키면 pytest 캡처가 시작 전 실패하므로 검증 시 Linux `/tmp`를 명시했다.
- `loaders` extra는 현재 환경에 `gdal-config`가 없어 설치 검증하지 않았다. T-013에서 GDAL Python binding 설치 환경과 함께 별도 검증한다.

**다음**: T-004 — 나머지 DTO(`geocode`, `reverse`, `search`, `zipcode`, `pobox`, `admin`)와 단위 테스트 작성.

---

## 2026-05-22 (human, 추가 명시)

**작업**: 사용자 추가 지시 반영 — 프로젝트/패키지 식별자 정정, WSL/NTFS 개발 정책, 데이터 위치(NTFS의 `data/`) 명시

**변경 파일**:
- 갱신: `README.md`, `AGENTS.md`, `SKILL.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/backend-package.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reflection-summary.md` 외 일괄 치환 대상 전부

**결정**:
- 식별자 통일: GitHub 저장소 = `python-kraddr-geo`, Python import = `kraddr.geo`, CLI = `kraddr-geo`, env prefix = `KRADDR_GEO_`, PostgreSQL DB = `kraddr_geo`, 프론트엔드 패키지 = `kraddr-geo-ui`
- PC 개발은 WSL ext4 위에서, 작업 완료 시 NTFS로 카피. 데이터(`data/`)는 NTFS 측에만 두고 ext4 작업 디렉토리는 심볼릭 링크/절대경로로 참조
- 테스트(특히 통합/e2e/전국 검증)는 NTFS의 `data/`를 reference로 삼는다

**참고**: 이번 변경은 코드를 새로 만들기 전 사양 단계에서의 명확화이며, ADR은 추가하지 않음(향후 결정이 뒤집힐 때 ADR로 별도 기록).

**다음**: T-001 (`pyproject.toml` 신규 작성). pyproject.toml의 `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`, importlinter `root_package = "kraddr.geo"`로 시작.

---

## 2026-05-22 (human)

**작업**: 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드)을 master 문서에 반영

**변경 파일**:
- 신규: `SKILL.md`, `CHANGELOG.md`
- 신규 (`docs/`): `architecture.md`, `decisions.md`, `data-model.md`, `tasks.md`, `resume.md`, `journal.md`, `backend-package.md`, `frontend-package.md`, `agent-guide.md`, `external-apis.md`
- 갱신: `AGENTS.md`, `README.md`, `docs/address-db-schema.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reverse-geocoding.md`, `docs/spatialite-vworld-implementation.md`
- 신규: `docs/reflection-summary.md` (반영 내용 요약)

**결정**:
- ADR-001 ~ ADR-006, ADR-013을 `docs/decisions.md`에 초기 기록
- 응답 구조는 vworld와 1:1 호환, 자체 확장은 `x_extension`만 (ADR-003)
- 라이브러리 API는 async-only (ADR-002)
- 로더는 GDAL Python binding 사용, `ogr2ogr` subprocess 폐기 (ADR-005)

**참고**: 첨부받은 두 docx 사양서가 우선이며, 기존 SpatiaLite 문서와 충돌하는 부분은 모두 PostgreSQL + PostGIS / `kraddr-geo` 기준으로 갱신함.

**다음**: T-001 (`pyproject.toml` 신규 작성).

---

## 2026-05-22 (human, 이전)

**작업**: 기존 SpatiaLite 기반 구현(`kraddr.geo`)을 `v1` 브랜치로 이관하고 master를 문서·repo 설정만 남도록 정리

**변경 파일**: 삭제 — `alembic/`, `alembic.ini`, `debug-ui/`, `pyproject.toml`, `src/`, `tests/`

**메모**: master는 새 사양으로 처음부터 다시 구현한다. 이전 구현은 `v1` 브랜치에서 참조 가능.
