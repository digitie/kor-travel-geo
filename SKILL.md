# SKILL — addr-kr 에이전트 매뉴얼

> 이 파일은 당신(AI 에이전트)이 작업을 시작하기 전 반드시 읽어야 한다.
> 1회만 읽으면 30분 이상의 디버깅을 줄일 수 있다.

## 1. 정체성

`addr-kr`은 도로명주소 전자지도(PDF 사양)를 PostGIS에 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**이다. vworld API의 응답 형식을 호환하면서 자체 확장(`x_extension`)을 더한다. UI 패키지(`addr-kr-ui`)는 별도이며, 이 저장소는 백엔드만 다룬다.

이전 SpatiaLite/SQLite 기반 구현(`kraddr.geo`)은 `v1` 브랜치에 보존되어 있다. master 브랜치는 PostgreSQL + PostGIS 기반 새 사양으로 재시작한다.

## 2. 빠른 시작

```bash
uv venv && uv pip install -e ".[api,loaders,dev]"
cp .env.example .env && $EDITOR .env       # ADDR_KR_PG_DSN 채우기
docker compose up -d postgres              # postgis/postgis:16-3.4
alembic upgrade head
addr-kr load all-sidos /data/jusoMap/202605 --mode full \
    --pg-conn "host=localhost dbname=addr_kr user=addr password=..."
uvicorn addr_kr.api.app:app --reload
```

## 3. 디렉토리 지도

```
src/addr_kr/
  dto/       — pydantic v2 입력/출력 (DB·FastAPI 의존성 없음)
  core/      — 비즈니스 로직 (Protocol에만 의존)
  infra/     — DB 어댑터 (SQLAlchemy 2 async, raw SQL)
  loaders/   — 파일 적재 (일반 쿼리 경로와 완전 분리)
  client.py  — AsyncAddressClient (라이브러리 API 진입점)
  api/       — FastAPI 라우터 (client.py를 호출)
  cli/       — typer CLI
```

의존 방향은 **dto → core → infra → client → api/cli** 한 방향. `import-linter`가 CI에서 강제한다.

## 4. 절대 하지 말 것 (DO NOT)

1. **의존 방향 역행 금지**: 위 계층 순서를 거스르는 import 금지. 역방향 import 시 import-linter가 CI에서 실패시킴.
2. **동기 인터페이스 추가 금지**: `AsyncAddressClient`만 둔다. 동기가 필요하면 호출자가 `asyncio.run`으로 감싼다.
3. **`pg_trgm.similarity_threshold` 전역 변경 금지**: 항상 트랜잭션 내부에서 `SET LOCAL`.
4. **ORM에 비즈니스 로직 금지**: `infra/models.py`는 매핑만. 쿼리는 `infra/*_repo.py`의 raw SQL에.
5. **좌표 순서 혼동 금지**: 모든 외부 인터페이스는 `(lon, lat)`. 내부 PostGIS도 `ST_MakePoint(lon, lat)`.
6. **MVM_RES_CD 매핑 하드코드 금지**: settings 또는 DB `load_codes` 테이블에서 읽는다.
7. **응답에 `x_extension` 외 자체 필드 추가 금지**: vworld 호환성을 깬다.
8. **외부 API 키 평문 커밋 금지**: 모두 `SecretStr`. `.env`는 권한 600 또는 systemd `EnvironmentFile`/vault.
9. **`ogr2ogr` subprocess 호출 금지**: GDAL Python binding(`gdal.VectorTranslate`) 사용. CP949 디코딩은 `open_options=["ENCODING=CP949"]`로 명시.
10. **프론트엔드 패키지에 DB 드라이버 추가 금지**: `addr-kr-ui`는 백엔드 REST API만 호출. `pg`, `prisma` 같은 의존성 들어오면 ADR 위반.

## 5. 자주 묻는 작업

| 작업 | 시작 파일 |
|------|-----------|
| 새 엔드포인트 추가 | `dto/<name>.py` → `core/<name>.py` → `infra/<name>_repo.py` → `api/routers/<name>.py` |
| 새 SQL 쿼리 튜닝 | `infra/*_repo.py`의 `_SQL` 상수. EXPLAIN은 `/debug/explain` UI |
| 새 적재 소스 추가 | `loaders/<name>_loader.py`, `manifest.py` 확장 |
| 응답 필드 추가 (자체 확장) | `dto/<name>.py`의 `*Extension` 클래스 |
| 새 에러 코드 추가 | `exceptions.py` + `api/responses.py` 매핑 |
| 외부 API 폴백 호출 | `httpx.AsyncClient` + `tenacity` 재시도. 키는 `Settings`에서 `SecretStr`로 |

## 6. 도메인 어휘

| 약어 | 의미 |
|------|------|
| BJD_CD | 법정동코드 10자리 (시도2 + 시군구3 + 읍면동3 + 리2) |
| RNCODE_FULL | 도로명코드 12자리 (SIG_CD 5 + RN_CD 7) |
| BD_MGT_SN | 건물관리번호 25자리, 전국 unique |
| BSI_ZON_NO | 건물의 기초구역번호 = 우편번호 5자리 |
| BAS_ID | `TL_KODIS_BAS`의 기초구역번호 = 우편번호 |
| MV | `mv_geocode_target` — 평면화된 머티리얼라이즈드 뷰 |
| MVM_RES_CD | 이동사유코드 (신규/수정/삭제) |
| MVMN_DE | 이동일자 YYYYMMDD |

## 7. 작업 후 체크리스트

- [ ] `pytest -q` 통과
- [ ] `ruff check .` / `mypy` / `lint-imports` 통과
- [ ] `docs/journal.md`에 작업 항목 추가 (역시간순)
- [ ] `docs/resume.md`의 진척도 갱신
- [ ] 의사결정이 있었다면 `docs/decisions.md`에 ADR 추가
- [ ] 사용자 가시 변경이면 `CHANGELOG.md` 갱신
- [ ] DTO/스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
